import os
from together import Together
from dotenv import load_dotenv

load_dotenv()

MODEL = os.environ.get("TOGETHER_MODEL", "zai-org/GLM-5.3-Flash")


def fix_article(article_md: str, issues: list[dict], atoms_by_source: dict) -> str:
    if not issues:
        return article_md

    issues_text = "\n".join(
        f"- [{issue['severity'].upper()}] {issue['detail']}"
        for issue in issues
    )
    all_atoms = "\n".join(
        f"Source: {url}\n" + "\n".join(texts)
        for url, texts in atoms_by_source.items()
    )
    
    prompt = f"""
    You are correcting an existing research article. It failed a quality evaluation.
    
    ### CRITICAL CORRECTION RULES:
    1. PRESERVE the original narrative and conceptual progression.
    2. DO NOT remove the '## Sources' section. If missing, add it with the provided URLs.
    3. If a section promises executable code (e.g., "Building from scratch"):
       - Include code ONLY when it is present in the source material.
       - If executable code is unavailable, DO NOT invent it. Instead, explain the implementation conceptually and revise the heading so it doesn't promise code.
    4. If a section is missing key concepts, expand it using the source material.
    5. Do NOT rewrite sections that already passed. Fix only the failures listed.
    
    ### FAILURES TO FIX:
    {issues_text}
    
    ### YOUR PREVIOUS DRAFT:
    {article_md}
    
    ### SOURCE MATERIAL:
    {all_atoms}
    
    After correction, return the COMPLETE, corrected article.
    """
    
    client = Together(timeout=600.0, max_retries=3)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        reasoning_effort="low",
        max_tokens=32768,
    )
    choice = response.choices[0] if response.choices else None
    content = getattr(choice.message, "content", None) if choice else None
    if not isinstance(content, str) or not content.strip():
        finish_reason = getattr(choice, "finish_reason", "no choices")
        raise RuntimeError(
            f"{MODEL} returned no revised article "
            f"(finish_reason={finish_reason!r})"
        )
    return content.strip()