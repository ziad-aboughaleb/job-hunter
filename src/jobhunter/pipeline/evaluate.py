import concurrent.futures
import os
import time

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
  api_key = os.getenv(settings.llm.api_key_env, "sk-dummy")

  return OpenAI(
    api_key=api_key,
    base_url=settings.llm.base_url,
  )


def load_pending_candidates() -> list[Candidate]:
  """Loads un-evaluated candidates from disk."""
  logger.info("Loading candidates for evaluation...")
  raw_data = read(DATA_PATH / "candidates.json", list)

  candidates = []
  for item in raw_data:
    try:
      candidates.append(Candidate(**item))
    except Exception as e:
      logger.error(f"Failed to parse candidate {item.get('uid', 'unknown')}: {e}")

  # Only evaluate jobs that haven't been processed yet
  pending = [c for c in candidates if c.status == "pending"]

  logger.info(f"Loaded {len(pending)} pending candidates out of {len(candidates)} total.")
  return pending


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

    # Pydantic strictly validates that the AI followed your schema
    eval_result = EvaluationResult.model_validate_json(raw_json)
    return candidate, eval_result

  except ValidationError as ve:
    logger.error(f"AI returned invalid schema for {candidate.company}: {ve}")
    return candidate, None
  except Exception as e:
    logger.error(f"LLM API error evaluating {candidate.company}: {e}")
    return candidate, None


def execute_evaluation_pipeline(client: OpenAI, candidates: list[Candidate], system_prompt: str) -> list[tuple[Candidate, EvaluationResult | None]]:
  """Runs evaluations concurrently with a rich progress bar."""

  # Be careful not to DDoS your LLM. Local models or strict APIs need lower concurrency.
  max_workers = 3
  results: list[tuple[Candidate, EvaluationResult | None]] = []

  console.print(f"[bold cyan]Evaluating {len(candidates)} jobs with AI...[/bold cyan]")

  with Progress(
    SpinnerColumn("dots", style="cyan"),
    TextColumn("{task.description}", table_column=Column(ratio=1)),
    TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
    BarColumn(bar_width=24, style="dim cyan", complete_style="green", finished_style="bold green"),
    TaskProgressColumn(),
    expand=True,
    console=console,
  ) as progress:
    eval_task = progress.add_task("[cyan]Evaluating...", total=len(candidates))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
      future_to_candidate = {executor.submit(evaluate_single_job, client, system_prompt, c): c for c in candidates}

      for future in concurrent.futures.as_completed(future_to_candidate):
        candidate = future_to_candidate[future]

        try:
          result = future.result()
          results.append(result)

          # Update UI
          company = candidate.company
          score = result[1].score if result[1] else "ERR"
          color = "green" if isinstance(score, int) and score >= settings.score_threshold else "yellow"

          progress.update(eval_task, advance=1, description=f"[cyan]Evaluating... [dim](Finished {company} - [{color}]{score}[/{color}][/dim])")
        except Exception as e:
          logger.exception(f"Unhandled error processing future for {candidate.company}: {e}")
          progress.update(eval_task, advance=1)

        # Simple delay to respect API rate limits
        time.sleep(settings.llm.request_delay)

    progress.update(eval_task, description="[bold green]Evaluation complete![/bold green]")

  return results


def process_and_save_results(results: list[tuple[Candidate, EvaluationResult | None]]):
  """Updates candidate status based on AI output and saves to disk."""
  logger.info("Processing LLM results and saving...")
  console.print("\n[dim cyan]Saving evaluated candidates to disk...[/dim cyan]")

  final_candidates = []
  passed = 0
  hard_failed = 0
  low_score = 0
  errors = 0

  for candidate, evaluation in results:
    if not evaluation:
      # Keep as pending if the AI API failed, so it retries next run
      errors += 1
      final_candidates.append(candidate)
      continue

    # Inject AI analysis into the Candidate model
    # (Assuming you add these fields to your Candidate schema, or store them in a dict)
    candidate.status = "evaluated"

    # You can attach the evaluation dict directly to the candidate for storage
    candidate_dict = candidate.model_dump()
    candidate_dict["evaluation"] = evaluation.model_dump()

    if evaluation.hard_fail:
      hard_failed += 1
    elif evaluation.score < settings.score_threshold:
      low_score += 1
    else:
      passed += 1

    final_candidates.append(candidate_dict)

  if final_candidates:
    write(DATA_PATH / "evaluated.json", final_candidates)
    # Optional: delete candidates.json if you want to clear the queue
    # delete(DATA_PATH / "candidates.json")

  return passed, hard_failed, low_score, errors


def print_summary(total: int, passed: int, hard_failed: int, low_score: int, errors: int):
  """Prints the final evaluation summary to the terminal."""
  console.print("\n[bold]AI Evaluation Summary[/bold]")
  console.print("──────────────────────────────")
  console.print(f"Total evaluated : [cyan]{total}[/cyan]")
  console.print(f"Passed          : [bold green]{passed}[/bold green]")
  console.print(f"Failed (Gates)  : [red]{hard_failed}[/red]")
  console.print(f"Failed (Score)  : [yellow]{low_score}[/yellow]")
  if errors:
    console.print(f"API Errors      : [bold red]{errors}[/bold red]")
  console.print("──────────────────────────────\n")


def main():
  """Orchestrates the AI evaluation pipeline."""
  logger.info("=== Starting AI Evaluation Pipeline ===")

  # 1. Setup
  client = setup_llm_client()
  candidates = load_pending_candidates()

  if not candidates:
    console.print("[yellow]No pending candidates to evaluate.[/yellow]")
    return

  # Build this ONCE, not inside the loop, to maximize local LLM caching
  system_prompt = build_system_prompt()

  # 2. Execute
  results = execute_evaluation_pipeline(client, candidates, system_prompt)

  # 3. Finalize & Save
  passed, hard_failed, low_score, errors = process_and_save_results(results)

  # 4. Report
  print_summary(len(candidates), passed, hard_failed, low_score, errors)
  logger.info("=== AI Evaluation Pipeline Finished ===")


if __name__ == "__main__":
  main()
