import concurrent.futures
import logging
import time

import openai
from openai import OpenAI
from pydantic import ValidationError
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Column

from jobhunter.core.logger import console
from jobhunter.core.paths import DATA_PATH, read, write
from jobhunter.core.settings import settings
from jobhunter.models import Candidate, EvaluatedCandidate, EvaluationResult
from jobhunter.tools.prompt import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


def setup_llm_client() -> OpenAI:
  """Initializes the OpenAI client (supports local Ollama/vLLM via base_url)."""
  logger.info("Initializing LLM client...")

  if not settings.llm_api_key:
    logger.error("LLM API key is missing. Set LLM_API_KEY in your .env file.")
    console.print("[bold red]Error: LLM API key is missing. Set LLM_API_KEY in your .env file.[/bold red]")
    raise ValueError("LLM_API_KEY is empty. Check your .env file.")

  return OpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm.base_url,
  )


def build_evaluation_tasks(job_uid: str | None = None) -> list[Candidate]:
  """Loads candidates from disk and filters for those pending evaluation."""
  logger.info("Building evaluation tasks...")

  raw_candidates = read(DATA_PATH / "candidates.json", list)
  raw_evals = read(DATA_PATH / "evaluated.json", list)

  evaluated_uids = {item.get("uid") for item in raw_evals if "uid" in item}

  tasks = []
  for item in raw_candidates:
    try:
      c = Candidate(**item)

      if job_uid:
        if c.uid == job_uid:
          tasks.append(c)
          break
        continue

      if c.uid not in evaluated_uids:
        tasks.append(c)
    except Exception as e:
      logger.error(f"Failed to parse candidate {item.get('uid', 'unknown')}: {e}")
      console.print(f"  [red]✖ Failed to parse candidate {item.get('uid', 'unknown')}[/red]")

  logger.info(f"Generated {len(tasks)} evaluation tasks from {len(raw_candidates)} total candidates.")

  return tasks


def evaluate_single_job(client: OpenAI, system_prompt: str, candidate: Candidate, retries: int = 5, backoff: float = 1.5) -> tuple[Candidate, EvaluationResult | None]:
  """Calls the LLM to evaluate a single job and parses the result with automatic retry and JSON cleanup fallbacks."""
  user_prompt = build_user_prompt(candidate)

  for attempt in range(retries):
    raw_json = ""

    try:
      response = client.chat.completions.create(
        model=settings.llm.model or "gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        response_format={"type": "json_object"},
        temperature=settings.llm.temperature,
        timeout=settings.llm.timeout,
      )

      raw_json = response.choices[0].message.content or ""
      if not raw_json:
        raise ValueError("LLM returned empty content instead of JSON.")

      try:
        eval_result = EvaluationResult.model_validate_json(raw_json)
        return candidate, eval_result

      except ValidationError:
        cleaned_json = raw_json.strip()
        if cleaned_json.startswith("```json"):
          cleaned_json = cleaned_json[7:]
        if cleaned_json.endswith("```"):
          cleaned_json = cleaned_json[:-3]
        cleaned_json = cleaned_json.strip()

        eval_result = EvaluationResult.model_validate_json(cleaned_json)
        return candidate, eval_result

    except openai.RateLimitError as rle:
      if attempt < retries - 1:
        sleep_time = backoff * (2**attempt)
        logger.warning(f"Rate limit hit (429) for {candidate.company}. Retrying in {sleep_time}s (Attempt {attempt + 1}/{retries})...")
        time.sleep(sleep_time)
      else:
        logger.error(f"Rate limit exceeded max retries for {candidate.company}: {rle}")
        console.print(f"  [red]✖ Rate limit exceeded for {candidate.company} after {retries} retries.[/red]")
        return candidate, None

    except openai.APIStatusError as ase:
      if ase.status_code >= 500 and attempt < retries - 1:
        sleep_time = backoff * (2**attempt)
        time.sleep(sleep_time)
      else:
        console.print("\n───────── API ERROR DETAILS ─────────")
        console.print(ase.response.json() if hasattr(ase, "response") else str(ase))
        console.print("───────────────────────────────────────\n")
        return candidate, None

    except ValidationError as ve:
      logger.error(f"AI returned invalid schema for {candidate.company}: {ve}")
      console.print(f"  [red]✖ AI returned invalid schema for {candidate.company}[/red]")
      logger.debug(f"Offending raw JSON for {candidate.company}:\n{raw_json}")
      return candidate, None

    except Exception as e:
      logger.error(f"LLM API error evaluating {candidate.company}: {e}")
      console.print(f"  [red]✖ LLM API error evaluating {candidate.company}: {e}[/red]")
      return candidate, None

  return candidate, None


def execute_evaluation_tasks(client: OpenAI, tasks: list[Candidate]) -> list[tuple[Candidate, EvaluationResult | None]]:
  """Executes the AI evaluation tasks concurrently with a Rich progress bar."""
  fetched_evals: list[tuple[Candidate, EvaluationResult | None]] = []
  system_prompt = build_system_prompt()
  target_total = len(tasks)

  workers = max(1, min(settings.workers.evaluation_workers, 20))

  logger.info(f"Executing evaluation tasks across {target_total} targets with {workers} workers.")
  console.print(f"[bold cyan]Evaluating {target_total} jobs with AI...[/bold cyan]")

  with Progress(
    SpinnerColumn("dots", style="cyan"),
    TextColumn("{task.description}", table_column=Column(ratio=1)),
    TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
    BarColumn(bar_width=24, style="dim cyan", complete_style="green", finished_style="bold green"),
    TaskProgressColumn(),
    expand=True,
    console=console,
  ) as progress:
    eval_task = progress.add_task("[cyan]Starting evaluation...", total=target_total)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
      future_to_candidate = {executor.submit(evaluate_single_job, client, system_prompt, candidate): candidate for candidate in tasks}

      for future in concurrent.futures.as_completed(future_to_candidate):
        candidate = future_to_candidate[future]
        name = candidate.company or "Unknown"

        try:
          result = future.result(timeout=settings.llm.timeout + 10)
          fetched_evals.append(result)

          if result[1] is not None:
            score = result[1].score
            color = "green" if score >= settings.evaluating.score_threshold else "yellow"
            progress.update(eval_task, advance=1, description=f"[cyan]Evaluating... [dim](Finished {name} - [{color}]{score}[/{color}][/dim])")
          else:
            progress.update(eval_task, advance=1)
            progress.console.print(f"  [dim red]⚠ API/Validation Error for {name}. Skipping...[/dim red]")

        except concurrent.futures.TimeoutError:
          logger.error(f"Task for {name} timed out.")
          console.print(f"  [red]✖ Evaluation for {name} timed out.[/red]")
          progress.update(eval_task, advance=1)

        except Exception as e:
          logger.exception(f"Error executing evaluation task for {name}: {e}")
          console.print(f"  [red]✖ Error evaluating {name}: {e}[/red]")
          progress.update(eval_task, advance=1)

        if settings.llm.request_delay > 0:
          time.sleep(settings.llm.request_delay)

    progress.update(eval_task, description="[bold green]Evaluation complete![/bold green]")

  success_count = sum(1 for _, eval_result in fetched_evals if eval_result is not None)

  logger.info(f"Successfully evaluated {success_count} jobs.")

  return fetched_evals


def format_evaluation_results(fetched_evals: list[tuple[Candidate, EvaluationResult | None]]) -> tuple[list[EvaluatedCandidate], int, int, int, int]:
  """Formats the AI results into EvaluatedCandidate models and calculates metrics."""
  logger.info("Formatting LLM results and calculating statistics...")
  console.print("[dim cyan]Formatting evaluations...[/dim cyan]")

  passed = hard_failed = low_score = errors = 0
  final_evaluations: list[EvaluatedCandidate] = []

  for candidate, evaluation in fetched_evals:
    if not evaluation:
      errors += 1
      continue

    candidate.status = "evaluated"

    evaluated_candidate = EvaluatedCandidate(**candidate.model_dump(), evaluation=evaluation)

    if evaluation.hard_fail:
      hard_failed += 1
      logger.debug(f"Candidate {candidate.company} hard failed gates.")
    elif evaluation.score < settings.evaluating.score_threshold:
      low_score += 1
      logger.debug(f"Candidate {candidate.company} failed score threshold ({evaluation.score}).")
    else:
      passed += 1

    final_evaluations.append(evaluated_candidate)

  logger.info(f"Formatting complete. {passed} passed, {hard_failed} hard failed, {low_score} low score, {errors} errors.")

  return final_evaluations, passed, hard_failed, low_score, errors


def save_evaluation_results(final_evaluations: list[EvaluatedCandidate]):
  """Saves evaluated candidates to disk, preventing duplicate UIDs, and sorts by score."""
  logger.info("Saving evaluations...")
  console.print("[dim cyan]Saving evaluations...[/dim cyan]")

  existing_evals = read(DATA_PATH / "evaluated.json", list)

  new_uids = {c.uid for c in final_evaluations}
  filtered_evals = [e for e in existing_evals if e.get("uid") not in new_uids]

  new_eval_dicts = [c.model_dump(mode="json") for c in final_evaluations]

  filtered_evals.extend(new_eval_dicts)
  filtered_evals.sort(key=lambda x: x.get("evaluation", {}).get("score", -1), reverse=True)

  write(DATA_PATH / "evaluated.json", filtered_evals)

  logger.info(f"Successfully saved {len(final_evaluations)} evaluations to disk.")


def main(job_uid: str | None = None):
  """Orchestrates the AI evaluation pipeline."""
  logger.info("Starting AI Evaluation Pipeline run.")

  client = setup_llm_client()

  tasks = build_evaluation_tasks(job_uid)
  if not tasks:
    logger.warning("No active candidates found to evaluate.")
    console.print("[yellow]No active candidates found to evaluate.[/yellow]")
    return

  fetched_evals = execute_evaluation_tasks(client, tasks)
  final_evaluations, passed, hard_failed, low_score, errors = format_evaluation_results(fetched_evals)

  if final_evaluations:
    save_evaluation_results(final_evaluations)

  total_successful = passed + hard_failed + low_score
  logger.info(f"Pipeline finished. Evaluated: {total_successful} | Passed: {passed} | Hard Failed: {hard_failed} | Low Score: {low_score} | Errors: {errors}")

  console.print("\n[bold]AI Evaluation Summary[/bold]")
  console.print("───────────────────────────────────────")
  console.print(f"Total evaluated : [cyan]{total_successful}[/cyan]")
  console.print(f"Passed          : [bold green]{passed}[/bold green]")
  console.print(f"Failed (Gates)  : [red]{hard_failed}[/red]")
  console.print(f"Failed (Score)  : [yellow]{low_score}[/yellow]")
  if errors:
    console.print(f"API Errors      : [bold red]{errors}[/bold red]")
  console.print("───────────────────────────────────────\n")
