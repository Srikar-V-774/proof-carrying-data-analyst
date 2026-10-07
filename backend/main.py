import uuid
from io import BytesIO
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analyzer import analyze
from data_quality import build_data_quality_report


load_dotenv()

app = FastAPI(title="Proof-Carrying Data Analyst")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

datasets = {}


class AnalysisRequest(BaseModel):
    dataset_id: str
    question: str


# ---------------------------------------------------------
# JSON-SAFE DATA CONVERSION
# ---------------------------------------------------------

def make_json_safe(df):
    """
    Convert Pandas values into JSON-safe Python values.

    Important:
    Pandas numeric columns normally keep missing values as NaN.
    NaN is not valid JSON, so we explicitly convert every missing
    value to None after converting the dataframe to object dtype.
    """

    safe_df = df.astype(object).where(
        pd.notna(df),
        None,
    )

    return safe_df.to_dict(orient="records")


# ---------------------------------------------------------
# BASIC ROUTES
# ---------------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Proof-Carrying Data Analyst API",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
    }


# ---------------------------------------------------------
# UPLOAD DATASET
# ---------------------------------------------------------

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename or ""

    if not filename.lower().endswith(
        (".csv", ".xlsx", ".xls")
    ):
        raise HTTPException(
            status_code=400,
            detail="Only CSV and Excel files are supported currently.",
        )

    try:
        contents = await file.read()

        if not contents:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        # -------------------------------------------------
        # READ FILE
        # -------------------------------------------------

        if filename.lower().endswith(".csv"):
            df = pd.read_csv(
                BytesIO(contents),
                keep_default_na=True,
            )
        else:
            df = pd.read_excel(
                BytesIO(contents)
            )

        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="The uploaded dataset is empty.",
            )

        dataset_id = str(uuid.uuid4())

        # -------------------------------------------------
        # STORE RAW DATA
        # -------------------------------------------------

        raw_path = DATA_DIR / f"{dataset_id}_raw.csv"

        df.to_csv(
            raw_path,
            index=False,
        )

        # -------------------------------------------------
        # BUILD QUALITY REPORT
        # -------------------------------------------------

        quality_report = build_data_quality_report(df)

        cleaned_df = quality_report.pop(
            "cleaned_dataframe"
        )

        # -------------------------------------------------
        # STORE CLEANED DATA
        # -------------------------------------------------

        cleaned_path = DATA_DIR / f"{dataset_id}_cleaned.csv"

        cleaned_df.to_csv(
            cleaned_path,
            index=False,
        )

        # -------------------------------------------------
        # STORE DATASET INFORMATION
        # -------------------------------------------------

        datasets[dataset_id] = {
            "filename": filename,
            "raw_path": str(raw_path),
            "cleaned_path": str(cleaned_path),
            "quality": quality_report,
        }

        # -------------------------------------------------
        # PREVIEW
        # -------------------------------------------------

        preview_df = df.head(5)

        preview = make_json_safe(
            preview_df
        )

        # -------------------------------------------------
        # RETURN
        # -------------------------------------------------

        return {
            "dataset_id": dataset_id,
            "filename": filename,

            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "column_names": [
                str(column)
                for column in df.columns
            ],

            "preview": preview,

            "quality_summary": {
                "duplicate_rows": quality_report[
                    "raw"
                ]["duplicates"]["count"],

                "duplicate_rows_involved": quality_report[
                    "raw"
                ]["duplicates"]["rows_involved"],

                "missing_cells": quality_report[
                    "raw"
                ]["missing"]["total_cells"],

                "columns_with_missing": len(
                    quality_report[
                        "raw"
                    ]["missing"]["by_column"]
                ),

                "mixed_type_columns": len(
                    quality_report[
                        "raw"
                    ]["mixed_types"]
                ),

                "cleaning_actions": len(
                    quality_report[
                        "cleaning"
                    ]["actions"]
                ),
            },
        }

    except HTTPException:
        raise

    except Exception as e:
        print("UPLOAD ERROR:", repr(e))

        raise HTTPException(
            status_code=400,
            detail=f"Could not read file: {str(e)}",
        )


# ---------------------------------------------------------
# DATA QUALITY REPORT
# ---------------------------------------------------------

@app.get("/dataset/{dataset_id}/quality")
def get_data_quality(dataset_id: str):

    dataset = datasets.get(dataset_id)

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found. Please upload the file again.",
        )

    return {
        "dataset_id": dataset_id,
        "filename": dataset["filename"],
        **dataset["quality"],
    }


# ---------------------------------------------------------
# DATASET ROWS
# ---------------------------------------------------------

@app.get("/dataset/{dataset_id}/rows")
def get_dataset_rows(
    dataset_id: str,
    view: str = "raw",
    sort_by: str = "",
    descending: bool = False,
    search: str = "",
):

    dataset = datasets.get(dataset_id)

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found. Please upload the file again.",
        )

    if view not in ("raw", "cleaned"):
        raise HTTPException(
            status_code=400,
            detail="View must be either 'raw' or 'cleaned'.",
        )

    try:

        # -------------------------------------------------
        # SELECT DATA SOURCE
        # -------------------------------------------------

        if view == "raw":
            path = dataset["raw_path"]
        else:
            path = dataset["cleaned_path"]

        df = pd.read_csv(
            path,
            keep_default_na=True,
        )

        # -------------------------------------------------
        # SEARCH
        # -------------------------------------------------

        if search.strip():

            search_text = search.strip()

            mask = df.astype(str).apply(
                lambda column: column.str.contains(
                    search_text,
                    case=False,
                    na=False,
                    regex=False,
                )
            ).any(axis=1)

            df = df.loc[mask]

        # -------------------------------------------------
        # SORT
        # -------------------------------------------------

        if sort_by:

            if sort_by not in df.columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Column '{sort_by}' does not exist.",
                )

            try:

                df = df.sort_values(
                    by=sort_by,
                    ascending=not descending,
                    kind="stable",
                )

            except Exception:

                df = (
                    df.astype({
                        sort_by: str
                    })
                    .sort_values(
                        by=sort_by,
                        ascending=not descending,
                        kind="stable",
                    )
                )

        # -------------------------------------------------
        # JSON-SAFE DATA
        # -------------------------------------------------

        data = make_json_safe(df)

        # -------------------------------------------------
        # RETURN
        # -------------------------------------------------

        return {
            "dataset_id": dataset_id,
            "filename": dataset["filename"],
            "view": view,

            "rows": int(len(df)),
            "columns": int(len(df.columns)),

            "column_names": [
                str(column)
                for column in df.columns
            ],

            "data": data,
        }

    except HTTPException:
        raise

    except Exception as e:

        print("ROWS ERROR:", repr(e))

        raise HTTPException(
            status_code=500,
            detail=f"Could not load dataset: {str(e)}",
        )


# ---------------------------------------------------------
# ANALYZE DATASET
# ---------------------------------------------------------

@app.post("/analyze")
def analyze_dataset(request: AnalysisRequest):

    if not request.question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty.",
        )

    dataset = datasets.get(
        request.dataset_id
    )

    if not dataset:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found. Please upload the file again.",
        )

    try:

        # -------------------------------------------------
        # CURRENT ANALYSIS SOURCE
        # -------------------------------------------------

        # Analysis currently uses the original raw dataset.
        #
        # The quality/cleaning workspace is intentionally
        # separate for now so the UI does not silently change
        # the mathematical source of an analysis.

        df = pd.read_csv(
            dataset["raw_path"],
            keep_default_na=True,
        )

        result = analyze(
            df=df,
            question=request.question.strip(),
        )

        return {
            "question": request.question.strip(),
            "filename": dataset["filename"],
            **result,
        }

    except Exception as e:

        print("ANALYSIS ERROR:", repr(e))

        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        )
