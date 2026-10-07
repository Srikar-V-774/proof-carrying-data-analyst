import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
from google import genai


MODEL = "gemini-3.5-flash-lite"


def clean_code(text: str) -> str:
    text = text.strip()

    match = re.search(
        r"```(?:python)?\s*(.*?)```",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    if match:
        text = match.group(1).strip()

    return text


def validate_code(code: str):
    forbidden_names = {
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "__import__",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
    }

    forbidden_modules = {
        "os",
        "sys",
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "shutil",
        "pathlib",
        "pickle",
        "builtins",
    }

    tree = ast.parse(code)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in {"pandas", "numpy"}:
                    raise ValueError(
                        f"Import not allowed: {alias.name}"
                    )

        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".")[0]

            if module not in {"pandas", "numpy"}:
                raise ValueError(
                    f"Import not allowed: {node.module}"
                )

        elif isinstance(node, ast.Name):
            if node.id in forbidden_names:
                raise ValueError(
                    f"Unsafe operation not allowed: {node.id}"
                )

        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ValueError(
                    "Private/dunder attributes are not allowed."
                )

    return True


def make_profile(df: pd.DataFrame):
    profile = {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "duplicate_rows": int(df.duplicated().sum()),
        "columns_detail": [],
        "sample_rows": df.head(8).fillna("").to_dict(orient="records"),
    }

    for column in df.columns:
        series = df[column]

        detail = {
            "name": str(column),
            "dtype": str(series.dtype),
            "missing": int(series.isna().sum()),
            "unique": int(series.nunique(dropna=True)),
        }

        # Give Gemini the actual categorical values.
        # This helps map "North", "South", etc. to the correct column.
        if series.dtype == "object" or str(series.dtype).startswith("string"):
            values = (
                series.dropna()
                .astype(str)
                .str.strip()
                .drop_duplicates()
                .tolist()
            )

            detail["categorical_values"] = values[:50]

        if pd.api.types.is_numeric_dtype(series):
            detail["min"] = float(series.min()) if not series.empty else None
            detail["max"] = float(series.max()) if not series.empty else None

        profile["columns_detail"].append(detail)

    return profile


def generate_code(question: str, profile: dict):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are the reasoning and code-generation engine of a
PROOF-CARRYING DATA ANALYST.

The user asks a natural-language question about a pandas DataFrame.

Your job is to translate the ENTIRE meaning of the question into
executable pandas code.

The Python code will be executed by another system.
Therefore you MUST NOT calculate or guess the answer yourself.

==================================================
CRITICAL DATA ANALYSIS RULES
==================================================

1. ROW ORDER HAS NO MEANING.

Never assume that rows are sorted, grouped, consecutive,
or in any particular order.

For example, if the user asks:

"What is the total in North?"

you MUST filter the appropriate categorical column for North
before calculating the total.

Never use row positions such as:
    df.head()
    df.iloc[:3]
    df.iloc[0:3]

unless the user explicitly asks about first/last rows.

2. USE THE USER'S COMPLETE QUESTION.

Every important condition in the question must affect the code.

Examples:

"What is the total amount?"
    -> sum amount

"What is the total amount in North?"
    -> filter North THEN sum amount

"What is the average amount in South?"
    -> filter South THEN mean amount

"How many orders are from North?"
    -> filter North THEN count rows

"What was the highest amount in Q2?"
    -> filter Q2 THEN max amount

Do NOT ignore location, category, date, quarter,
customer, product, region, or other constraints.

3. MAP NATURAL LANGUAGE TO REAL COLUMNS.

Use the DATASET PROFILE to determine which column contains
the requested concept.

For example:

"North" may correspond to:
    region

"Q2" may correspond to:
    quarter

"amount" may correspond to:
    amount

Never invent a column.

4. MATCH CATEGORICAL VALUES ROBUSTLY.

Uploaded data may contain:

North
north
 NORTH
North

or accidental surrounding whitespace.

For categorical comparisons, prefer normalized comparison such as:

df["region"].astype(str).str.strip().str.casefold() == "north"

Do NOT rely on exact capitalization when the user's intent
clearly matches a categorical value.

5. DATA MAY BE MESSY.

The dataset may contain:
- shuffled rows
- missing values
- extra whitespace
- inconsistent capitalization
- duplicate rows
- mixed data types
- inconsistent date formatting

Never rely on row order.

6. MISSING DATA.

If missing values make the requested calculation impossible,
return:

result = "CANNOT DETERMINE"

Do not invent missing values.

7. DUPLICATES.

Do not automatically remove duplicates.

Determine from the question and dataset whether duplicates
represent legitimate records or possible duplicate observations.

Never silently change the dataset merely because duplicate rows exist.

8. NUMERIC VALUES.

Only perform numeric calculations on numeric data.

9. EXACT RESULT VARIABLE.

The final result MUST be assigned to:

result

10. NO FILE ACCESS.

The generated code must NOT:
- read files
- write files
- access the internet
- use operating-system commands
- use subprocess
- use network libraries

11. ALLOWED LIBRARIES.

Only pandas and numpy are allowed.

12. OUTPUT.

Return ONLY Python code.

No Markdown.
No explanation.
No answer sentence.

==================================================
USER QUESTION
==================================================

{question}

==================================================
DATASET PROFILE
==================================================

{json.dumps(profile, indent=2, default=str)}

==================================================
IMPORTANT EXAMPLES
==================================================

Question:
"What is the total in North?"

Correct pattern:

mask = (
    df["region"]
    .astype(str)
    .str.strip()
    .str.casefold()
    == "north"
)

result = df.loc[mask, "amount"].sum()

Question:
"What is the average amount in South?"

Correct pattern:

mask = (
    df["region"]
    .astype(str)
    .str.strip()
    .str.casefold()
    == "south"
)

result = df.loc[mask, "amount"].mean()

Question:
"How many orders are from North?"

Correct pattern:

mask = (
    df["region"]
    .astype(str)
    .str.strip()
    .str.casefold()
    == "north"
)

result = int(mask.sum())

Question:
"What is the total amount?"

Correct pattern:

result = df["amount"].sum()

==================================================

FINAL REQUIREMENT

Before producing code, mentally identify:

1. What operation is requested?
2. What numeric/text field is requested?
3. What filters or conditions are requested?
4. Which real dataset columns represent those conditions?
5. Does row order matter? It must NOT matter unless explicitly requested.

Then generate the pandas code.

Return ONLY the code.
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )

    code = clean_code(response.text)

    validate_code(code)

    if not re.search(r"\bresult\s*=", code):
        raise ValueError(
            "Generated code does not assign a result variable."
        )

    return code


def execute_code(code: str, df: pd.DataFrame):

    validate_code(code)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        data_path = temp_path / "data.csv"
        script_path = temp_path / "analysis.py"

        df.to_csv(data_path, index=False)

        safe_builtins = """
SAFE_BUILTINS = {
    "len": len,
    "min": min,
    "max": max,
    "sum": sum,
    "round": round,
    "abs": abs,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "range": range,
    "enumerate": enumerate,
}
"""

        script = f"""
import json
import pandas as pd
import numpy as np

{safe_builtins}

df = pd.read_csv({str(data_path)!r})

namespace = {{
    "__builtins__": SAFE_BUILTINS,
    "pd": pd,
    "np": np,
    "df": df,
}}

code = {code!r}

exec(code, namespace)

if "result" not in namespace:
    raise RuntimeError("Analysis code did not produce result.")

result = namespace["result"]

def clean(value):

    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, pd.Series):
        return value.fillna("").to_dict()

    if isinstance(value, pd.DataFrame):
        return value.fillna("").to_dict(orient="records")

    if isinstance(value, dict):
        return {{str(k): clean(v) for k, v in value.items()}}

    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return value

print(json.dumps(clean(result), default=str))
"""

        script_path.write_text(script)

        completed = subprocess.run(
            [sys.executable, "-I", str(script_path)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=temp_dir,
            env={
                "PATH": os.environ.get("PATH", ""),
            },
        )

        if completed.returncode != 0:
            raise RuntimeError(
                completed.stderr.strip()
                or "Analysis execution failed."
            )

        output = completed.stdout.strip()

        if not output:
            raise RuntimeError("Analysis produced no result.")

        return json.loads(output)


def analyze(df: pd.DataFrame, question: str):

    profile = make_profile(df)

    code = generate_code(question, profile)

    first_result = execute_code(code, df)

    second_result = execute_code(code, df)

    first_normalized = json.dumps(
        first_result,
        sort_keys=True,
        default=str,
    )

    second_normalized = json.dumps(
        second_result,
        sort_keys=True,
        default=str,
    )

    verified = first_normalized == second_normalized

    if first_result == "CANNOT DETERMINE":
        status = "CANNOT DETERMINE"
    elif verified:
        status = "VERIFIED"
    else:
        status = "WARNING"

    return {
        "status": status,
        "answer": first_result,
        "code": code,
        "verification": {
            "first_execution": first_result,
            "second_execution": second_result,
            "match": verified,
        },
        "profile": profile,
    }
