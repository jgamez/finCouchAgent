"""
Heuristic check that a free-form topic is plausibly about personal financial education.
Preset lesson topics from the form are always accepted.
"""

from __future__ import annotations

import re

# Must match the `value` attributes of preset topic options in web/templates/index.html
PRESET_TOPICS: frozenset[str] = frozenset(
    {
        "budgeting",
        "saving",
        "investing",
        "credit",
        "compound interest",
        "taxes",
        "insurance",
        "student loans",
        "entrepreneurship",
        "cryptocurrency",
    }
)

# Substring checks (longer phrases first in sorted order)
_FINANCIAL_PHRASES: tuple[str, ...] = tuple(
    dict.fromkeys(
        sorted(
            [
                "personal finance",
                "money management",
                "financial literacy",
                "financial planning",
                "emergency fund",
                "compound interest",
                "stock market",
                "index fund",
                "mutual fund",
                "debit card",
                "credit card",
                "credit score",
                "student loan",
                "car loan",
                "auto loan",
                "mortgage",
                "refinance",
                "side hustle",
                "gross pay",
                "net pay",
                "payroll tax",
                "paycheck",
                "savings account",
                "checking account",
                "debt snowball",
                "interest rate",
                "annual percentage",
                "income tax",
                "capital gains",
                "gig economy",
                "gig work",
                "roth ira",
                "traditional ira",
                "health savings",
                "529 plan",
                "federal student",
                "fafsa",
                "wage",
                "salary",
                "inflation",
                "recession",
                "diversify",
                "diversif",
                "rebalancing",
                "rebalance",
            ],
            key=len,
            reverse=True,
        )
    )
)

# Single tokens from user text (3+ characters, or known short finance abbrev below)
_FINANCIAL_WORDS: frozenset[str] = frozenset(
    {
        "reit",
        "money",
        "finances",
        "finance",
        "financial",
        "fiscal",
        "income",
        "expense",
        "expenses",
        "cash",
        "banking",
        "bank",
        "savings",
        "saving",
        "save",
        "budget",
        "budgets",
        "budgeting",
        "invest",
        "investing",
        "investment",
        "investor",
        "stock",
        "stocks",
        "bond",
        "bonds",
        "securities",
        "etf",
        "etfs",
        "crypto",
        "bitcoin",
        "ethereum",
        "debit",
        "lender",
        "lending",
        "loan",
        "loans",
        "lend",
        "borrow",
        "debt",
        "mortgage",
        "interest",
        "overdraft",
        "taxes",
        "tax",
        "refund",
        "irs",
        "withholding",
        "deduct",
        "deducts",
        "fico",
        "wealth",
        "retirement",
        "insurance",
        "entrepreneur",
        "entrepreneurship",
        "profit",
        "revenue",
        "startup",
        "frugal",
        "spending",
        "401k",
        "apy",
        "apr",
        "hsa",
        "ira",
        "iras",
        "wage",
        "salary",
        "wages",
        "inflation",
        "tuition",
        "pension",
        "annuity",
        "amortization",
    }
)

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# also allow "401k" when split wrong
_EXTRA_PHRASES: tuple[str, ...] = ("401k", "401(k)", "w-2", "w-4", "1099", "h.s.a.")


def is_financial_education_topic(text: str) -> bool:
    """
    Return True if the topic is one of the preset list values, or
    the text appears to be about money / personal finance (heuristic).
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    if t in PRESET_TOPICS:
        return True
    for phrase in _FINANCIAL_PHRASES:
        if len(phrase) >= 3 and phrase in t:
            return True
    for extra in _EXTRA_PHRASES:
        ex = extra.replace(".", "").lower()
        if ex in t.replace(".", ""):
            return True
    # e.g. "ETF" / "HSA" / "IRA" (3–4 char instruments) before length gate
    for w in _TOKEN.findall(t):
        w = w.lower()
        if w in _FINANCIAL_WORDS:
            return True
    if len(t) < 4:
        return False
    return False
