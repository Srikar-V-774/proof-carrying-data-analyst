import re
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------
# BASIC HELPERS
# ---------------------------------------------------------

def is_missing(value):
    if pd.isna(value):
        return True

    if isinstance(value, str):
        return value.strip() == ""

    return False


def clean_column_name(column):
    """
    Make column names easier to work with while preserving meaning.
    Example:
        " Customer Name " -> "Customer Name"
    """
    return str(column).strip()


def looks_numeric(series):
    """
    Determine whether a mostly-text column is actually numeric data.
    """
    if series.empty:
        return False

    non_missing = series.dropna().astype(str).str.strip()

    if len(non_missing) == 0:
        return False

    cleaned = (
        non_missing
        .str.replace(",", "", regex=False)
        .str.replace(r"[$€£₹]", "", regex=True)
        .str.replace("%", "", regex=False)
        .str.strip()
    )

    converted = pd.to_numeric(cleaned, errors="coerce")

    valid_ratio = converted.notna().mean()

    return valid_ratio >= 0.90


def looks_date(series):
    """
    Conservatively detect whether a column appears to contain dates.
    """
    if series.empty:
        return False

    non_missing = series.dropna().astype(str).str.strip()

    if len(non_missing) == 0:
        return False

    date_pattern = re.compile(
        r"("
        r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}"
        r"|"
        r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}"
        r"|"
        r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}"
        r")"
    )

    matching = non_missing.apply(
        lambda value: bool(date_pattern.search(value))
    )

    return matching.mean() >= 0.80


# ---------------------------------------------------------
# CATEGORICAL NORMALIZATION
# ---------------------------------------------------------

def normalize_categorical_series(series):
    """
    Conservative normalization:
    - trims whitespace
    - collapses repeated internal whitespace
    - detects obvious capitalization variants

    Example:
        " North "
        "north"
        "NORTH"

    become:

        "North"
    """

    original = series.copy()

    normalized = series.copy()

    normalized = normalized.map(
        lambda value: (
            value.strip()
            if isinstance(value, str)
            else value
        )
    )

    normalized = normalized.map(
        lambda value: (
            re.sub(r"\s+", " ", value)
            if isinstance(value, str)
            else value
        )
    )

    # Build groups by lowercase representation.
    groups = {}

    for value in normalized.dropna().unique():
        if not isinstance(value, str):
            continue

        key = value.casefold()

        if key not in groups:
            groups[key] = []

        groups[key].append(value)

    replacements = {}

    for key, values in groups.items():
        unique_values = list(dict.fromkeys(values))

        if len(unique_values) <= 1:
            continue

        # Pick the most readable representation.
        preferred = None

        for value in unique_values:
            if value.istitle():
                preferred = value
                break

        if preferred is None:
            preferred = max(
                unique_values,
                key=lambda value: sum(character.isupper() for character in value),
            )

        for value in unique_values:
            replacements[value] = preferred

    normalized = normalized.replace(replacements)

    changed = []

    for index in series.index:
        before = original.loc[index]
        after = normalized.loc[index]

        if not is_missing(before) and not is_missing(after):
            if str(before) != str(after):
                changed.append({
                    "row": int(index) + 1,
                    "before": str(before),
                    "after": str(after),
                })

    return normalized, changed


# ---------------------------------------------------------
# DATA QUALITY ANALYSIS
# ---------------------------------------------------------

def profile_dataset(df):
    """
    Inspect the dataset without modifying the original dataframe.
    """

    working = df.copy()

    # Clean column-name whitespace for analysis.
    original_columns = list(working.columns)

    cleaned_columns = [
        clean_column_name(column)
        for column in working.columns
    ]

    column_name_changes = []

    for before, after in zip(original_columns, cleaned_columns):
        if str(before) != str(after):
            column_name_changes.append({
                "before": str(before),
                "after": str(after),
            })

    working.columns = cleaned_columns

    # -----------------------------------------------------
    # DUPLICATES
    # -----------------------------------------------------

    exact_duplicate_mask = working.duplicated(keep=False)

    exact_duplicate_count = int(
        working.duplicated(keep="first").sum()
    )

    duplicate_groups = []

    if exact_duplicate_mask.any():
        duplicate_df = working.loc[exact_duplicate_mask]

        groups = duplicate_df.groupby(
            list(working.columns),
            dropna=False,
            sort=False,
        )

        for _, group in groups:
            if len(group) > 1:
                duplicate_groups.append({
                    "count": int(len(group)),
                    "rows": [int(index) + 1 for index in group.index],
                    "data": group.fillna("").to_dict(
                        orient="records"
                    ),
                })

    # -----------------------------------------------------
    # MISSING VALUES
    # -----------------------------------------------------

    missing_by_column = {}

    for column in working.columns:
        missing_count = int(
            working[column].apply(is_missing).sum()
        )

        if missing_count > 0:
            missing_by_column[column] = missing_count

    total_missing_cells = sum(
        missing_by_column.values()
    )

    # -----------------------------------------------------
    # COLUMN DETAILS
    # -----------------------------------------------------

    columns_detail = []

    for column in working.columns:
        series = working[column]

        dtype = str(series.dtype)

        if pd.api.types.is_numeric_dtype(series):
            detected_type = "numeric"

        elif looks_date(series):
            detected_type = "date"

        elif looks_numeric(series):
            detected_type = "numeric-like"

        elif pd.api.types.is_bool_dtype(series):
            detected_type = "boolean"

        else:
            detected_type = "text / categorical"

        unique_count = int(
            series.dropna().astype(str).nunique()
        )

        missing_count = int(
            series.apply(is_missing).sum()
        )

        detail = {
            "name": column,
            "original_dtype": dtype,
            "detected_type": detected_type,
            "missing": missing_count,
            "unique": unique_count,
        }

        if detected_type in (
            "text / categorical",
            "boolean",
        ):
            values = (
                series
                .dropna()
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
            )

            detail["sample_values"] = values[:30]

        if pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(
                series,
                errors="coerce",
            )

            if numeric.notna().any():
                detail["min"] = float(numeric.min())
                detail["max"] = float(numeric.max())

        columns_detail.append(detail)

    # -----------------------------------------------------
    # SUSPICIOUS MIXED TYPES
    # -----------------------------------------------------

    mixed_type_columns = []

    for column in working.columns:
        series = working[column].dropna()

        if len(series) == 0:
            continue

        types = set(type(value).__name__ for value in series)

        if len(types) > 1:
            mixed_type_columns.append({
                "column": column,
                "types": sorted(types),
            })

    # -----------------------------------------------------
    # RETURN REPORT
    # -----------------------------------------------------

    return {
        "rows": int(len(working)),
        "columns": int(len(working.columns)),
        "column_names": list(working.columns),

        "duplicates": {
            "count": exact_duplicate_count,
            "rows_involved": int(exact_duplicate_mask.sum()),
            "groups": duplicate_groups[:100],
        },

        "missing": {
            "total_cells": int(total_missing_cells),
            "by_column": missing_by_column,
        },

        "mixed_types": mixed_type_columns,

        "column_name_changes": column_name_changes,

        "columns_detail": columns_detail,
    }


# ---------------------------------------------------------
# CLEAN DATASET
# ---------------------------------------------------------

def clean_dataset(df):
    """
    Produce a conservative cleaned representation.

    Important:
    We DO NOT silently delete duplicates.
    We DO NOT fill missing values.
    We DO NOT guess currencies.
    We DO NOT guess ambiguous dates.

    The purpose is normalization, not fabrication.
    """

    cleaned = df.copy()

    cleaning_actions = []
    transformations = []

    # -----------------------------------------------------
    # COLUMN NAMES
    # -----------------------------------------------------

    old_columns = list(cleaned.columns)

    new_columns = [
        clean_column_name(column)
        for column in cleaned.columns
    ]

    if old_columns != new_columns:
        cleaned.columns = new_columns

        cleaning_actions.append({
            "type": "column_names",
            "description": "Trimmed whitespace from column names.",
        })

    # -----------------------------------------------------
    # WHITESPACE + CATEGORICAL NORMALIZATION
    # -----------------------------------------------------

    for column in cleaned.columns:
        series = cleaned[column]

        if (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):
            normalized, changes = normalize_categorical_series(
                series
            )

            if changes:
                cleaned[column] = normalized

                cleaning_actions.append({
                    "type": "categorical_normalization",
                    "column": column,
                    "changes": len(changes),
                    "description": (
                        f"Normalized whitespace/capitalization "
                        f"variants in '{column}'."
                    ),
                    "examples": changes[:20],
                })

                transformations.extend([
                    {
                        "column": column,
                        **change,
                    }
                    for change in changes[:100]
                ])

    # -----------------------------------------------------
    # NUMERIC-LIKE COLUMNS
    # -----------------------------------------------------

    for column in cleaned.columns:
        series = cleaned[column]

        if not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):
            continue

        if not looks_numeric(series):
            continue

        original = series.copy()

        numeric_text = (
            series
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace(r"[$€£₹]", "", regex=True)
            .str.replace("%", "", regex=False)
            .str.strip()
        )

        converted = pd.to_numeric(
            numeric_text,
            errors="coerce",
        )

        # Only convert if almost all non-missing values converted.
        original_non_missing = ~series.apply(is_missing)

        if original_non_missing.sum() == 0:
            continue

        successful = converted.notna() & original_non_missing

        ratio = successful.sum() / original_non_missing.sum()

        if ratio >= 0.90:
            cleaned[column] = converted

            cleaning_actions.append({
                "type": "numeric_conversion",
                "column": column,
                "description": (
                    f"Converted '{column}' to numeric values."
                ),
                "success_ratio": round(float(ratio), 3),
            })

    # -----------------------------------------------------
    # DO NOT REMOVE DUPLICATES
    # -----------------------------------------------------

    duplicate_count = int(
        cleaned.duplicated(keep="first").sum()
    )

    if duplicate_count > 0:
        cleaning_actions.append({
            "type": "duplicates_preserved",
            "count": duplicate_count,
            "description": (
                "Duplicate rows were detected but not deleted "
                "automatically."
            ),
        })

    # -----------------------------------------------------
    # DO NOT FILL MISSING VALUES
    # -----------------------------------------------------

    missing_cells = int(
        cleaned.apply(
            lambda column: column.apply(is_missing).sum()
        ).sum()
    )

    if missing_cells > 0:
        cleaning_actions.append({
            "type": "missing_values_preserved",
            "count": missing_cells,
            "description": (
                "Missing values were detected and preserved. "
                "No values were invented."
            ),
        })

    # -----------------------------------------------------
    # FINAL REPORT
    # -----------------------------------------------------

    quality_after = profile_dataset(cleaned)

    return cleaned, {
        "actions": cleaning_actions,
        "transformations": transformations,
        "duplicates_preserved": duplicate_count,
        "missing_values_preserved": missing_cells,
        "quality_after": quality_after,
    }


# ---------------------------------------------------------
# BUILD COMPLETE DATASET REPORT
# ---------------------------------------------------------

def build_data_quality_report(df):
    """
    Create raw profile + cleaned dataset + cleaning report.
    """

    raw_profile = profile_dataset(df)

    cleaned_df, cleaning_report = clean_dataset(df)

    return {
        "raw": raw_profile,
        "cleaned": cleaning_report["quality_after"],
        "cleaning": cleaning_report,
        "cleaned_dataframe": cleaned_df,
    }