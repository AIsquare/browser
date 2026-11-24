import re
from typesafe_sdk import Noul, TypeSafeClient
from dotenv import load_dotenv

load_dotenv()

def evaluate_article(article_md: str, manifests: list[dict], atoms_by_source: dict) -> dict:
    if not isinstance(article_md, str) or not article_md.strip():
        return {
            "evaluation_status": "failed",
            "issues": [{"severity": "critical", "dimension": "format", "detail": "Draft text is empty."}]
        }

    client = TypeSafeClient()
    issues = []
    evaluation_status = "complete"

    # 1. Deterministic: Basic Traceability
    if "## Sources" not in article_md and "Sources:" not in article_md:
        issues.append({"severity": "major", "dimension": "traceability", "detail": "Missing 'Sources' section."})
    elif "http" not in article_md:
        issues.append({"severity": "major", "dimension": "traceability", "detail": "No source URLs found."})

    # 2. Semantic Content Checks
    parts = re.split(r'^##\s+(.+)$', article_md, flags=re.MULTILINE)
    for i in range(1, len(parts) - 1, 2):
        title = parts[i].strip()
        body = parts[i + 1].strip()
        
        if not body: continue

        # Deterministic Code Check
        heading_lower = title.lower()
        if "scratch" in heading_lower or "implementation" in heading_lower or "how to" in heading_lower:
            if "```" not in body:
                issues.append({
                    "severity": "critical", "dimension": "completeness",
                    "detail": f"Section '{title}' promises implementation, but contains no code blocks."
                })
                continue # Skip JEV if deterministic check already failed

        # JEV Check: Explicitly listing the 5 P0 dimensions
        q = {
            "fulfills": Noul(
                instructions=(
                    "Evaluate this section against these criteria:\n"
                    "1. Completeness: Are important concepts missing?\n"
                    "2. Organization: Does the explanation progress logically?\n"
                    "3. Synthesis: Are related ideas connected rather than listed independently?\n"
                    "4. Factual grounding: Are technical explanations internally consistent and supported by the sources?\n"
                    "5. Narrative: Is the explanation clear and understandable?\n"
                    "Also, does the section fulfill its heading?\n"
                    "Return a score from 0 to 1."
                )
            )
        }
        try:
            # Pass the FULL body, not just the first 2000 chars
            r = client.system_one(state={"heading": title, "text": body}, questions=q)
            score = r.nouls["fulfills"].noul
            if score < 0.45:
                issues.append({
                    "severity": "major", "dimension": "content_quality",
                    "detail": f"Section '{title}' failed quality eval. Score: {score}"
                })
        except Exception as e:
            # FIX: Add a critical issue if JEV times out so it doesn't pass silently!
            evaluation_status = "failed"
            issues.append({
                "severity": "critical", "dimension": "evaluation",
                "detail": f"JEV evaluation failed for section '{title}': {e}"
            })

    return {"evaluation_status": evaluation_status, "issues": issues}