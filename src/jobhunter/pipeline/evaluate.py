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
    raise ValueError("LLM_API_KEY is empty. Check your .env file.")

  return OpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm.base_url,
  )


def build_evaluation_tasks() -> list[Candidate]:
  """Loads candidates from disk and filters for those pending evaluation."""
  logger.info("Building evaluation tasks...")

  raw_candidates = read(DATA_PATH / "candidates.json", list)
  raw_evals = read(DATA_PATH / "evaluated.json", list)

  evaluated_uids = {item.get("uid") for item in raw_evals if "uid" in item}

  tasks = []
  for item in raw_candidates:
    try:
      c = Candidate(**item)
      if c.uid not in evaluated_uids:
        tasks.append(c)
    except Exception as e:
      logger.error(f"Failed to parse candidate {item.get('uid', 'unknown')}: {e}")

  logger.info(f"Generated {len(tasks)} evaluation tasks from {len(raw_candidates)} total candidates.")

  return tasks


def evaluate_single_job(client: OpenAI, system_prompt: str, candidate: Candidate) -> tuple[Candidate, EvaluationResult | None]:
  """Calls the LLM to evaluate a single job and parses the result."""
  user_prompt = build_user_prompt(candidate)

  try:
    response = client.chat.completions.create(
      model=settings.llm.model or "gpt-4o-mini",
      messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
      response_format={"type": "json_object"},
      temperature=settings.llm.temperature,
      timeout=settings.llm.timeout,
    )

    raw_json = response.choices[0].message.content
    if not raw_json:
      raise ValueError("LLM returned empty content instead of JSON.")

    eval_result = EvaluationResult.model_validate_json(raw_json)
    return candidate, eval_result

  except openai.BadRequestError as e:
    console.print("\n───────── API ERROR DETAILS ─────────")
    console.print(e.response.json())
    console.print("───────────────────────────────────────\n")
    raise
  except ValidationError as ve:
    logger.error(f"AI returned invalid schema for {candidate.company}: {ve}")
    return candidate, None
  except Exception as e:
    logger.error(f"LLM API error evaluating {candidate.company}: {e}")
    return candidate, None


def execute_evaluation_tasks(client: OpenAI, tasks: list[Candidate]) -> list[tuple[Candidate, EvaluationResult | None]]:
  """Executes the AI evaluation tasks concurrently with a Rich progress bar."""
  fetched_evals: list[tuple[Candidate, EvaluationResult | None]] = []
  system_prompt = build_system_prompt()
  max_workers = settings.llm.max_workers
  target_total = len(tasks)
  candidate_iter = iter(tasks)

  logger.info(f"Executing evaluation tasks across {target_total} targets with {max_workers} workers.")
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
      future_to_candidate = {}

      def submit_next():
        try:
          c = next(candidate_iter)
          future = executor.submit(evaluate_single_job, client, system_prompt, c)
          future_to_candidate[future] = c
        except StopIteration:
          pass

      for _ in range(min(max_workers, target_total)):
        submit_next()

      while future_to_candidate:
        done, _ = concurrent.futures.wait(future_to_candidate.keys(), return_when=concurrent.futures.FIRST_COMPLETED)

        for future in done:
          candidate = future_to_candidate.pop(future)
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
            fetched_evals.append((candidate, None))
            progress.update(eval_task, advance=1)
            progress.console.print(f"  [dim red]⚠ Timeout for {name}. Skipping...[/dim red]")

          except Exception as e:
            logger.exception(f"Error executing evaluation task for {name}: {e}")
            fetched_evals.append((candidate, None))
            progress.update(eval_task, advance=1)
            progress.console.print(f"  [bold red]✖ Thread crashed for {name}[/bold red]")

          submit_next()
        time.sleep(settings.llm.request_delay)

    progress.update(eval_task, description="[bold green]Evaluation complete![/bold green]")

  success_count = sum(1 for _, eval_result in fetched_evals if eval_result is not None)

  logger.info(f"Successfully evaluated {success_count} jobs.")

  return fetched_evals


def format_evaluation_results(fetched_evals: list[tuple[Candidate, EvaluationResult | None]]) -> tuple[list[dict], int, int, int, int]:
  """Formats the AI results into final dictionaries and calculates metrics."""
  logger.info("Formatting LLM results and calculating statistics...")
  console.print("[dim cyan]Formatting evaluations...[/dim cyan]")

  passed = hard_failed = low_score = errors = 0
  final_evaluations = []

  for candidate, evaluation in fetched_evals:
    if not evaluation:
      errors += 1
      continue

    candidate.status = "evaluated"

    evaluated_candidate = EvaluatedCandidate(
      **candidate.model_dump(),
      evaluation=evaluation
    )

    if evaluation.hard_fail:
      hard_failed += 1
      logger.debug(f"Candidate {candidate.company} hard failed gates.")
    elif evaluation.score < settings.evaluating.score_threshold:
      low_score += 1
      logger.debug(f"Candidate {candidate.company} failed score threshold ({evaluation.score}).")
    else:
      passed += 1

    final_evaluations.append(evaluated_candidate.model_dump(mode="json"))

  logger.info(f"Formatting complete. {passed} passed, {hard_failed} hard failed, {low_score} low score, {errors} errors.")

  return final_evaluations, passed, hard_failed, low_score, errors


def save_evaluation_results(final_evaluations: list[dict]):
  """Saves evaluated candidates to disk and sorts by score."""
  logger.info("Saving evaluations...")
  console.print("[dim cyan]Saving evaluations...[/dim cyan]")

  existing_evals = read(DATA_PATH / "evaluated.json", list)
  existing_evals.extend(final_evaluations)

  existing_evals.sort(key=lambda x: x.get("evaluation", {}).get("score", -1), reverse=True)

  write(DATA_PATH / "evaluated.json", existing_evals)

  logger.info(f"Successfully saved {len(final_evaluations)} evaluations to disk.")


def main():
  """Orchestrates the AI evaluation pipeline."""
  logger.info("Starting AI Evaluation Pipeline run.")

  client = setup_llm_client()

  tasks = build_evaluation_tasks()
  if not tasks:
    logger.warning("No active candidates found to evaluate.")
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
