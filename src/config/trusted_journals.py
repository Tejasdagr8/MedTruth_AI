"""
Authoritative journal registry for MedTruth AI.
Each entry carries ISSNs, DOI prefix, normalized name variants, and authority tier.

Tier 1 = highest authority (Cochrane, WHO, landmark journals)
Tier 2 = top peer-reviewed journals (AHA, NEJM, JAMA, BMJ, Lancet …)
Tier 3 = solid domain-specific journals
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JournalEntry:
    canonical_name: str
    issns: frozenset[str]             # both print and electronic
    doi_prefix: str                   # publisher-level DOI prefix
    name_variants: frozenset[str]     # lowercase substrings to match against raw journal field
    impact_factor_normalized: float  # IF / 80, capped at 1.0
    authority_tier: int               # 1 = highest, 3 = lowest trusted
    authority_org: str                # "AHA", "WHO", "Cochrane", etc.


# ── AHA Journals ─────────────────────────────────────────────────────────────
# All published by Wolters Kluwer / Lippincott under DOI prefix 10.1161
# Impact factors sourced from 2023 JCR

AHA_JOURNALS: list[JournalEntry] = [
    JournalEntry(
        canonical_name="Circulation",
        issns=frozenset({"0009-7322", "1524-4539"}),
        doi_prefix="10.1161",
        name_variants=frozenset({"circulation"}),
        impact_factor_normalized=min(1.0, 37.8 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Circulation Research",
        issns=frozenset({"0009-7330", "1524-4571"}),
        doi_prefix="10.1161",
        name_variants=frozenset({"circulation research"}),
        impact_factor_normalized=min(1.0, 20.1 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Stroke",
        issns=frozenset({"0039-2499", "1524-4628"}),
        doi_prefix="10.1161",
        name_variants=frozenset({"stroke"}),
        impact_factor_normalized=min(1.0, 10.2 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Hypertension",
        issns=frozenset({"0194-911X", "1524-4563"}),
        doi_prefix="10.1161",
        name_variants=frozenset({"hypertension"}),
        impact_factor_normalized=min(1.0, 8.3 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Journal of the American Heart Association",
        issns=frozenset({"2047-9980"}),
        doi_prefix="10.1161",
        name_variants=frozenset({
            "journal of the american heart association",
            "jaha",
        }),
        impact_factor_normalized=min(1.0, 5.5 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Arteriosclerosis, Thrombosis, and Vascular Biology",
        issns=frozenset({"1079-5642", "1524-4636"}),
        doi_prefix="10.1161",
        name_variants=frozenset({
            "arteriosclerosis, thrombosis, and vascular biology",
            "arteriosclerosis thrombosis vascular biology",
            "atvb",
        }),
        impact_factor_normalized=min(1.0, 10.4 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Circulation: Heart Failure",
        issns=frozenset({"1941-3289", "1941-3297"}),
        doi_prefix="10.1161",
        name_variants=frozenset({"circulation: heart failure", "circulation heart failure"}),
        impact_factor_normalized=min(1.0, 8.1 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Circulation: Arrhythmia and Electrophysiology",
        issns=frozenset({"1941-3149", "1941-3084"}),
        doi_prefix="10.1161",
        name_variants=frozenset({
            "circulation: arrhythmia and electrophysiology",
            "circulation arrhythmia electrophysiology",
        }),
        impact_factor_normalized=min(1.0, 8.5 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Circulation: Cardiovascular Imaging",
        issns=frozenset({"1941-9651", "1942-0080"}),
        doi_prefix="10.1161",
        name_variants=frozenset({
            "circulation: cardiovascular imaging",
            "circulation cardiovascular imaging",
        }),
        impact_factor_normalized=min(1.0, 7.4 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Circulation: Cardiovascular Interventions",
        issns=frozenset({"1941-7640", "1941-7632"}),
        doi_prefix="10.1161",
        name_variants=frozenset({
            "circulation: cardiovascular interventions",
            "circulation cardiovascular interventions",
        }),
        impact_factor_normalized=min(1.0, 7.1 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Circulation: Cardiovascular Quality and Outcomes",
        issns=frozenset({"1941-7713", "1941-7705"}),
        doi_prefix="10.1161",
        name_variants=frozenset({
            "circulation: cardiovascular quality and outcomes",
            "circulation cardiovascular quality outcomes",
        }),
        impact_factor_normalized=min(1.0, 5.2 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
    JournalEntry(
        canonical_name="Circulation: Genomic and Precision Medicine",
        issns=frozenset({"2574-8300"}),
        doi_prefix="10.1161",
        name_variants=frozenset({
            "circulation: genomic and precision medicine",
            "circulation genomic precision medicine",
        }),
        impact_factor_normalized=min(1.0, 6.0 / 80),
        authority_tier=2,
        authority_org="AHA",
    ),
]

# ── All authority organizations ───────────────────────────────────────────────
ALL_AUTHORITY_JOURNALS: list[JournalEntry] = AHA_JOURNALS
# Future: extend with ESC, ACC, ASH, etc.

AHA_ISSNS: frozenset[str] = frozenset(
    issn for j in AHA_JOURNALS for issn in j.issns
)

AHA_DOI_PREFIX = "10.1161"

AHA_NAME_VARIANTS: frozenset[str] = frozenset(
    v for j in AHA_JOURNALS for v in j.name_variants
)


def lookup_journal(journal_name: str) -> JournalEntry | None:
    """Return the JournalEntry matching a raw journal name, or None."""
    j = journal_name.lower().strip()
    for entry in ALL_AUTHORITY_JOURNALS:
        if any(variant in j for variant in entry.name_variants):
            return entry
    return None


def is_aha_journal(journal_name: str) -> bool:
    entry = lookup_journal(journal_name)
    return entry is not None and entry.authority_org == "AHA"
