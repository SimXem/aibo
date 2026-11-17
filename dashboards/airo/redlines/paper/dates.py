"""Month/year formatting for paper presentation; source dates stay exact."""
from datetime import date
import re


def month_year(value: str) -> str:
    return date.fromisoformat(value[:7] + "-01").strftime("%B %Y")


def format_dates(text: str) -> str:
    return re.sub(r"\b\d{4}-\d{2}(?:-\d{2})?\b",
                  lambda match: month_year(match.group()), text)
