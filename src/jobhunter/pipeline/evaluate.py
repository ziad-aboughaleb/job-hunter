import concurrent.futures
import time

import openai
from openai import OpenAI
from pydantic import ValidationError
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Column

from jobhunter.core.logger import console, get_logger
from jobhunter.core.paths import DATA_PATH, read, write
from jobhunter.core.settings import settings
from jobhunter.models import Candidate, EvaluationResult
from jobhunter.tools.prompt import build_system_prompt, build_user_prompt

logger = get_logger(__name__, log_to_console=False)


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


def load_all_candidates() -> list[Candidate]:
  """Loads all candidates from disk."""
  logger.info("Loading candidates...")
  raw_data = read(DATA_PATH / "candidates.json", list)

  candidates = []
  for item in raw_data:
    try:
      candidates.append(Candidate(**item))
    except Exception as e:
      logger.error(f"Failed to parse candidate {item.get('uid', 'unknown')}: {e}")

  return candidates


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
    console.print("\n--- API ERROR DETAILS ---")
    console.print(e.response.json())
    console.print("-------------------------\n")
    raise
  except ValidationError as ve:
    logger.error(f"AI returned invalid schema for {candidate.company}: {ve}")
    return candidate, None
  except Exception as e:
    logger.error(f"LLM API error evaluating {candidate.company}: {e}")
    return candidate, None


def execute_evaluation_pipeline(client: OpenAI, candidates: list[Candidate], system_prompt: str) -> list[tuple[Candidate, EvaluationResult | None]]:
  """Runs evaluations concurrently for all provided candidates."""

  max_workers = settings.llm.max_workers
  results: list[tuple[Candidate, EvaluationResult | None]] = []

  target_total = len(candidates)
  candidate_iter = iter(candidates)

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
        """Helper to pull the next candidate and submit it to the pool."""
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

          try:
            result = future.result()
            results.append(result)

            if result[1] is not None:
              company = candidate.company
              score = result[1].score
              color = "green" if score >= settings.evaluating.score_threshold else "yellow"

              progress.update(eval_task, advance=1, description=f"[cyan]Evaluating... [dim](Finished {company} - [{color}]{score}[/{color}][/dim])")
            else:
              progress.update(eval_task, advance=1)
              progress.console.print(f"  [dim red]⚠ API Error for {candidate.company}. Skipping...[/dim red]")

          except Exception as e:
            logger.exception(f"Unhandled error for {candidate.company}: {e}")
            progress.update(eval_task, advance=1)

          submit_next()

        time.sleep(settings.llm.request_delay)

    progress.update(eval_task, description="[bold green]Evaluation complete![/bold green]")

  return results


def process_and_save_results(results: list[tuple[Candidate, EvaluationResult | None]], all_candidates: list[Candidate]) -> tuple[int, int, int, int]:
  """Saves successful evals to evaluation.json and keeps remaining in candidates.json."""
  logger.info("Processing LLM results and saving...")
  console.print("[dim cyan]Saving evaluated candidates to disk...[/dim cyan]")

  passed = 0
  hard_failed = 0
  low_score = 0
  errors = 0

  evaluated_data = read(DATA_PATH / "evaluated.json", list)
  evaluated_uids = set()

  for candidate, evaluation in results:
    if not evaluation:
      errors += 1
      continue

    candidate.status = "evaluated"
    evaluated_uids.add(candidate.uid)

    candidate_dict = candidate.model_dump()
    evaluation_dict = evaluation.model_dump()

    ordered_dict = {}
    for k, v in candidate_dict.items():
      if k == "ref":
        ordered_dict["evaluation"] = evaluation_dict
      ordered_dict[k] = v

    if "evaluation" not in ordered_dict:
      ordered_dict["evaluation"] = evaluation_dict

    candidate_dict = ordered_dict

    if evaluation.hard_fail:
      hard_failed += 1
    elif evaluation.score < settings.evaluating.score_threshold:
      low_score += 1
    else:
      passed += 1

    evaluated_data.append(candidate_dict)

  if evaluated_data:
    write(DATA_PATH / "evaluated.json", evaluated_data)
    logger.info("Successfully appended to evaluated.json.")

  remaining_candidates = [c.model_dump() for c in all_candidates if c.uid not in evaluated_uids]
  write(DATA_PATH / "candidates.json", remaining_candidates)

  return passed, hard_failed, low_score, errors


def main():
  """Orchestrates the AI evaluation pipeline."""
  logger.info("Starting AI Evaluation Pipeline...")

  client = setup_llm_client()
  all_candidates = load_all_candidates()

  pending_candidates = [c for c in all_candidates if c.status == "pending"]

  if not pending_candidates:
    console.print("[yellow]No pending candidates to evaluate.[/yellow]")
    return

  system_prompt = build_system_prompt()

  results = execute_evaluation_pipeline(client, pending_candidates, system_prompt)

  passed, hard_failed, low_score, errors = process_and_save_results(results, all_candidates)

  total_successful = passed + hard_failed + low_score
  logger.info(f"Evaluation pipeline completed. Successful: {total_successful} | Passed: {passed} | Hard Failed: {hard_failed} | Low Score: {low_score} | Errors: {errors}")

  console.print("\n[bold]AI Evaluation Summary[/bold]")
  console.print("──────────────────────────────")
  console.print(f"Total evaluated : [cyan]{total_successful}[/cyan]")
  console.print(f"Passed          : [bold green]{passed}[/bold green]")
  console.print(f"Failed (Gates)  : [red]{hard_failed}[/red]")
  console.print(f"Failed (Score)  : [yellow]{low_score}[/yellow]")
  if errors:
    console.print(f"API Errors      : [bold red]{errors}[/bold red]")
  console.print("──────────────────────────────\n")
