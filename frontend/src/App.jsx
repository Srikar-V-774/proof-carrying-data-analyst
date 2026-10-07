import { useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";

function App() {
  const [file, setFile] = useState(null);
  const [dataset, setDataset] = useState(null);
  const [uploading, setUploading] = useState(false);

  const [question, setQuestion] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState(null);

  const [error, setError] = useState("");

  // -------------------------------------------------------
  // DATA VIEWER
  // -------------------------------------------------------

  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewer, setViewer] = useState("raw");
  const [viewerRows, setViewerRows] = useState([]);
  const [viewerColumns, setViewerColumns] = useState([]);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [viewerSearch, setViewerSearch] = useState("");
  const [viewerSort, setViewerSort] = useState("");
  const [viewerDescending, setViewerDescending] = useState(false);

  // -------------------------------------------------------
  // QUALITY REPORT
  // -------------------------------------------------------

  const [quality, setQuality] = useState(null);
  const [qualityLoading, setQualityLoading] = useState(false);

  // -------------------------------------------------------
  // UPLOAD
  // -------------------------------------------------------

  async function handleUpload(event) {
    const selectedFile = event.target.files?.[0];

    if (!selectedFile) return;

    setFile(selectedFile);
    setDataset(null);
    setAnalysis(null);
    setQuality(null);
    setViewerRows([]);
    setError("");
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch(`${API_URL}/upload`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Upload failed.");
      }

      setDataset(data);

      // Fetch complete quality report after upload.
      await loadQuality(data.dataset_id);
    } catch (err) {
      setError(err.message || "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  // -------------------------------------------------------
  // QUALITY REPORT
  // -------------------------------------------------------

  async function loadQuality(datasetId) {
    setQualityLoading(true);

    try {
      const response = await fetch(
        `${API_URL}/dataset/${datasetId}/quality`
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not load quality report.");
      }

      setQuality(data);
    } catch (err) {
      setError(err.message || "Could not load quality report.");
    } finally {
      setQualityLoading(false);
    }
  }

  // -------------------------------------------------------
  // LOAD RAW / CLEANED DATA
  // -------------------------------------------------------

  async function loadViewerData(
    view = viewer,
    search = viewerSearch,
    sortBy = viewerSort,
    descending = viewerDescending
  ) {
    if (!dataset?.dataset_id) return;

    setViewerLoading(true);

    try {
      const params = new URLSearchParams();

      params.set("view", view);

      if (search.trim()) {
        params.set("search", search.trim());
      }

      if (sortBy) {
        params.set("sort_by", sortBy);
        params.set("descending", String(descending));
      }

      const response = await fetch(
        `${API_URL}/dataset/${dataset.dataset_id}/rows?${params.toString()}`
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not load dataset.");
      }

      setViewerRows(data.data || []);
      setViewerColumns(data.column_names || []);
    } catch (err) {
      setError(err.message || "Could not load dataset.");
    } finally {
      setViewerLoading(false);
    }
  }

  async function openViewer(view = "raw") {
    setViewer(view);
    setViewerSearch("");
    setViewerSort("");
    setViewerDescending(false);
    setViewerOpen(true);

    await loadViewerData(view, "", "", false);
  }

  async function changeViewer(view) {
    setViewer(view);
    setViewerSearch("");
    setViewerSort("");
    setViewerDescending(false);

    await loadViewerData(view, "", "", false);
  }

  async function handleViewerSearch(event) {
    const value = event.target.value;

    setViewerSearch(value);

    await loadViewerData(
      viewer,
      value,
      viewerSort,
      viewerDescending
    );
  }

  async function handleSortChange(event) {
    const value = event.target.value;

    setViewerSort(value);

    await loadViewerData(
      viewer,
      viewerSearch,
      value,
      viewerDescending
    );
  }

  async function toggleSortDirection() {
    const nextDirection = !viewerDescending;

    setViewerDescending(nextDirection);

    if (viewerSort) {
      await loadViewerData(
        viewer,
        viewerSearch,
        viewerSort,
        nextDirection
      );
    }
  }

  // -------------------------------------------------------
  // ANALYSIS
  // -------------------------------------------------------

  async function handleAnalyze() {
    if (!dataset?.dataset_id) {
      setError("Please upload a dataset first.");
      return;
    }

    if (!question.trim()) {
      setError("Please enter a question.");
      return;
    }

    setError("");
    setAnalysis(null);
    setAnalyzing(true);

    try {
      const response = await fetch(`${API_URL}/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          dataset_id: dataset.dataset_id,
          question: question.trim(),
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Analysis failed.");
      }

      setAnalysis(data);
    } catch (err) {
      setError(err.message || "Analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  // -------------------------------------------------------
  // FORMATTERS
  // -------------------------------------------------------

  function formatAnswer(answer) {
    if (typeof answer === "number") {
      return answer.toLocaleString();
    }

    if (typeof answer === "object" && answer !== null) {
      return JSON.stringify(answer, null, 2);
    }

    return String(answer);
  }

  function qualityStatus() {
    if (!quality) return "CHECKING";

    const duplicateCount =
      quality.raw?.duplicates?.count || 0;

    const missingCount =
      quality.raw?.missing?.total_cells || 0;

    const mixedTypes =
      quality.raw?.mixed_types?.length || 0;

    if (duplicateCount > 0 || missingCount > 0 || mixedTypes > 0) {
      return "REVIEW";
    }

    return "CLEAN";
  }

  // -------------------------------------------------------
  // UI
  // -------------------------------------------------------

  return (
    <div className="app">
      <nav className="navbar">
        <div>
          <div className="brand">PROOFCARRY</div>
          <div className="brand-subtitle">
            Proof-Carrying Data Analyst
          </div>
        </div>

        <div className="system-status">
          <span className="status-dot"></span>
          System Ready
        </div>
      </nav>

      <main>
        {/* HERO */}

        <section className="hero">
          <div className="hero-badge">
            AI DATA ANALYSIS · VERIFIED
          </div>

          <h1>
            Ask your data.
            <br />
            <span>Trust the answer.</span>
          </h1>

          <p>
            Upload your data, inspect its quality, ask a
            natural-language question, and receive an answer
            backed by executable and independently verified
            analysis.
          </p>
        </section>

        {/* WORKSPACE */}

        <section className="workspace">
          {/* UPLOAD */}

          <div className="card upload-card">
            <div className="card-label">
              01 · DATA SOURCE
            </div>

            <h2>Upload your dataset</h2>

            <p className="card-description">
              CSV and Excel files are currently supported.
            </p>

            <label className="upload-box">
              <input
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={handleUpload}
              />

              <div className="upload-icon">↑</div>

              <strong>
                {uploading
                  ? "Reading and checking dataset..."
                  : file
                    ? file.name
                    : "Choose a CSV or Excel file"}
              </strong>

              <span>
                {uploading
                  ? "Running data quality checks"
                  : "Click to browse your files"}
              </span>
            </label>

            {dataset && (
              <div className="dataset-success">
                <div className="success-icon">✓</div>

                <div>
                  <strong>{dataset.filename}</strong>

                  <span>
                    {dataset.rows.toLocaleString()} rows ·{" "}
                    {dataset.columns} columns
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* QUESTION */}

          <div className="card question-card">
            <div className="card-label">
              02 · ASK YOUR DATA
            </div>

            <h2>What do you want to know?</h2>

            <p className="card-description">
              Ask a question in natural language. The analysis
              engine will generate and execute reproducible
              code.
            </p>

            <textarea
              className="question-input"
              placeholder="Example: What is the total amount?"
              value={question}
              onChange={(event) =>
                setQuestion(event.target.value)
              }
              disabled={!dataset || analyzing}
            />

            <button
              className="analyze-button"
              onClick={handleAnalyze}
              disabled={
                !dataset ||
                !question.trim() ||
                analyzing
              }
            >
              {analyzing ? (
                <>
                  <span className="button-spinner"></span>
                  Analyzing...
                </>
              ) : (
                <>
                  Analyze Data
                  <span>→</span>
                </>
              )}
            </button>
          </div>
        </section>

        {/* ERROR */}

        {error && (
          <div className="error-box">
            <span>!</span>
            {error}
          </div>
        )}

        {/* DATASET QUALITY */}

        {dataset && (
          <section className="section">
            <div className="section-heading">
              <div>
                <div className="card-label">
                  DATA QUALITY
                </div>

                <h2>
                  Understand your dataset
                </h2>
              </div>

              <div className="dataset-meta">
                {dataset.rows.toLocaleString()} rows ·{" "}
                {dataset.columns} columns
              </div>
            </div>

            {/* QUALITY SUMMARY */}

            <div className="quality-summary-grid">
              <div className="quality-stat">
                <span className="quality-stat-label">
                  ROWS
                </span>

                <strong>
                  {dataset.rows.toLocaleString()}
                </strong>

                <small>
                  Records detected
                </small>
              </div>

              <div className="quality-stat">
                <span className="quality-stat-label">
                  COLUMNS
                </span>

                <strong>
                  {dataset.columns}
                </strong>

                <small>
                  Fields detected
                </small>
              </div>

              <div className="quality-stat">
                <span className="quality-stat-label">
                  DUPLICATES
                </span>

                <strong>
                  {dataset.quality_summary?.duplicate_rows ??
                    0}
                </strong>

                <small>
                  Repeated records
                </small>
              </div>

              <div className="quality-stat">
                <span className="quality-stat-label">
                  MISSING
                </span>

                <strong>
                  {dataset.quality_summary?.missing_cells ??
                    0}
                </strong>

                <small>
                  Empty cells
                </small>
              </div>
            </div>

            {/* QUALITY STATUS */}

            <div className="quality-status-card">
              <div>
                <div className="quality-status-title">
                  DATASET STATUS
                </div>

                <strong>
                  {qualityLoading
                    ? "Checking dataset..."
                    : qualityStatus()}
                </strong>
              </div>

              <div className="quality-status-description">
                {qualityStatus() === "REVIEW"
                  ? "Potential data-quality issues were detected. Review them before relying on analytical results."
                  : "No immediate quality problems were detected."}
              </div>
            </div>

            {/* DATA ACTIONS */}

            <div className="data-view-actions">
              <button
                className="data-view-button"
                onClick={() => openViewer("raw")}
              >
                <span>▤</span>
                View Raw Data
              </button>

              <button
                className="data-view-button"
                onClick={() => openViewer("cleaned")}
              >
                <span>✓</span>
                View Cleaned Data
              </button>
            </div>

            {/* QUALITY REPORT */}

            {quality && (
              <div className="quality-report">
                <div className="quality-report-header">
                  <div>
                    <div className="card-label">
                      QUALITY REPORT
                    </div>

                    <h3>
                      What the system found
                    </h3>
                  </div>
                </div>

                {/* DUPLICATES */}

                <div className="quality-report-block">
                  <div className="quality-block-heading">
                    <strong>
                      Duplicate records
                    </strong>

                    <span>
                      {quality.raw?.duplicates?.count || 0}
                    </span>
                  </div>

                  {quality.raw?.duplicates?.count > 0 ? (
                    <>
                      <p>
                        The dataset contains repeated
                        records. They were detected but
                        <strong> not automatically deleted</strong>.
                      </p>

                      <div className="duplicate-groups">
                        {quality.raw.duplicates.groups
                          .slice(0, 5)
                          .map((group, index) => (
                            <div
                              className="duplicate-group"
                              key={index}
                            >
                              <strong>
                                Duplicate group {index + 1}
                              </strong>

                              <span>
                                Rows:{" "}
                                {group.rows.join(", ")}
                              </span>

                              <span>
                                Repeated{" "}
                                {group.count} times
                              </span>
                            </div>
                          ))}
                      </div>
                    </>
                  ) : (
                    <p className="quality-good">
                      No exact duplicate rows detected.
                    </p>
                  )}
                </div>

                {/* MISSING */}

                <div className="quality-report-block">
                  <div className="quality-block-heading">
                    <strong>
                      Missing values
                    </strong>

                    <span>
                      {quality.raw?.missing?.total_cells ||
                        0}
                    </span>
                  </div>

                  {Object.keys(
                    quality.raw?.missing?.by_column || {}
                  ).length > 0 ? (
                    <div className="missing-list">
                      {Object.entries(
                        quality.raw.missing.by_column
                      ).map(([column, count]) => (
                        <div
                          className="missing-item"
                          key={column}
                        >
                          <span>{column}</span>
                          <strong>
                            {count}
                          </strong>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="quality-good">
                      No missing values detected.
                    </p>
                  )}

                  {quality.raw?.missing?.total_cells > 0 && (
                    <p>
                      Missing values are preserved. The
                      system will not invent data to fill
                      them.
                    </p>
                  )}
                </div>

                {/* MIXED TYPES */}

                <div className="quality-report-block">
                  <div className="quality-block-heading">
                    <strong>
                      Data type issues
                    </strong>

                    <span>
                      {quality.raw?.mixed_types?.length ||
                        0}
                    </span>
                  </div>

                  {quality.raw?.mixed_types?.length > 0 ? (
                    <div className="missing-list">
                      {quality.raw.mixed_types.map(
                        (item) => (
                          <div
                            className="missing-item"
                            key={item.column}
                          >
                            <span>
                              {item.column}
                            </span>

                            <strong>
                              {item.types.join(", ")}
                            </strong>
                          </div>
                        )
                      )}
                    </div>
                  ) : (
                    <p className="quality-good">
                      No obvious mixed-type columns detected.
                    </p>
                  )}
                </div>

                {/* CLEANING ACTIONS */}

                <div className="quality-report-block">
                  <div className="quality-block-heading">
                    <strong>
                      Cleaning performed
                    </strong>

                    <span>
                      {quality.cleaning?.actions?.length ||
                        0}
                    </span>
                  </div>

                  {quality.cleaning?.actions?.length > 0 ? (
                    <div className="cleaning-list">
                      {quality.cleaning.actions.map(
                        (action, index) => (
                          <div
                            className="cleaning-item"
                            key={index}
                          >
                            <span>✓</span>

                            <div>
                              <strong>
                                {action.description}
                              </strong>

                              {action.column && (
                                <small>
                                  Column:{" "}
                                  {action.column}
                                </small>
                              )}

                              {action.count !== undefined && (
                                <small>
                                  Count:{" "}
                                  {action.count}
                                </small>
                              )}
                            </div>
                          </div>
                        )
                      )}
                    </div>
                  ) : (
                    <p className="quality-good">
                      No automatic normalization was necessary.
                    </p>
                  )}
                </div>

                {/* IMPORTANT RULES */}

                <div className="data-rules">
                  <div className="data-rule">
                    <span>↔</span>
                    <div>
                      <strong>
                        Row order is ignored
                      </strong>
                      <small>
                        Analysis is based on values and
                        relationships, not the order of rows.
                      </small>
                    </div>
                  </div>

                  <div className="data-rule">
                    <span>!</span>
                    <div>
                      <strong>
                        Duplicates are not silently removed
                      </strong>
                      <small>
                        Repeated records are reported so the
                        system does not destroy legitimate
                        transactions.
                      </small>
                    </div>
                  </div>

                  <div className="data-rule">
                    <span>?</span>
                    <div>
                      <strong>
                        Missing information is not invented
                      </strong>
                      <small>
                        If missing or ambiguous data prevents
                        a reliable answer, the system can
                        refuse to determine it.
                      </small>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>
        )}

        {/* ANALYSIS RESULT */}

        {analysis && (
          <section className="result-section">
            <div className="result-header">
              <div>
                <div className="card-label">
                  03 · PROOF
                </div>

                <h2>
                  Analysis result
                </h2>
              </div>

              <div
                className={`verification-badge ${
                  analysis.status === "VERIFIED"
                    ? "verified"
                    : analysis.status ===
                        "CANNOT DETERMINE"
                      ? "cannot"
                      : "warning"
                }`}
              >
                <span>
                  {analysis.status === "VERIFIED"
                    ? "✓"
                    : analysis.status ===
                        "CANNOT DETERMINE"
                      ? "?"
                      : "!"}
                </span>

                {analysis.status}
              </div>
            </div>

            <div className="answer-card">
              <div className="answer-label">
                ANSWER
              </div>

              <div className="answer-value">
                {formatAnswer(analysis.answer)}
              </div>

              <div className="question-echo">
                “{analysis.question}”
              </div>
            </div>

            <div className="proof-grid">
              <div className="proof-card">
                <div className="proof-title">
                  <span className="proof-icon">
                    ⌘
                  </span>

                  Executable analysis
                </div>

                <pre>
                  <code>{analysis.code}</code>
                </pre>
              </div>

              <div className="proof-card">
                <div className="proof-title">
                  <span className="proof-icon">
                    ✓
                  </span>

                  Verification evidence
                </div>

                <div className="execution-row">
                  <span>
                    Execution 1
                  </span>

                  <strong>
                    {formatAnswer(
                      analysis.verification
                        .first_execution
                    )}
                  </strong>
                </div>

                <div className="execution-row">
                  <span>
                    Execution 2
                  </span>

                  <strong>
                    {formatAnswer(
                      analysis.verification
                        .second_execution
                    )}
                  </strong>
                </div>

                <div className="match-row">
                  <span>
                    Results match
                  </span>

                  <strong>
                    {analysis.verification.match
                      ? "YES ✓"
                      : "NO"}
                  </strong>
                </div>
              </div>
            </div>

            <div className="trust-strip">
              <div>
                <span>UNDERSTOOD</span>
                <strong>
                  Natural-language question
                </strong>
              </div>

              <div>
                <span>EXECUTED</span>
                <strong>
                  Python / Pandas
                </strong>
              </div>

              <div>
                <span>VERIFIED</span>
                <strong>
                  Independent re-execution
                </strong>
              </div>
            </div>
          </section>
        )}

        {/* HOW IT WORKS */}

        {!analysis && (
          <section className="trust-section">
            <div className="card-label">
              WHY PROOFCARRY
            </div>

            <h2>
              AI proposes.
              <br />
              <span>Code proves.</span>
            </h2>

            <div className="trust-grid">
              <div>
                <div className="trust-number">
                  01
                </div>

                <h3>
                  Understand
                </h3>

                <p>
                  Gemini interprets the question and
                  identifies the required data operation.
                </p>
              </div>

              <div>
                <div className="trust-number">
                  02
                </div>

                <h3>
                  Clean & Execute
                </h3>

                <p>
                  Python and Pandas inspect, normalize and
                  calculate using the uploaded dataset.
                </p>
              </div>

              <div>
                <div className="trust-number">
                  03
                </div>

                <h3>
                  Verify
                </h3>

                <p>
                  The generated analysis is executed again
                  and the results are compared before the
                  answer is trusted.
                </p>
              </div>
            </div>
          </section>
        )}
      </main>

      <footer>
        <span>PROOFCARRY</span>
        <span>
          Proof-Carrying Data Analyst · HNX26PSI08
        </span>
      </footer>

      {/* -------------------------------------------------
          DATA VIEWER MODAL
      -------------------------------------------------- */}

      {viewerOpen && (
        <div
          className="data-modal-backdrop"
          onClick={() => setViewerOpen(false)}
        >
          <div
            className="data-modal"
            onClick={(event) =>
              event.stopPropagation()
            }
          >
            <div className="data-modal-header">
              <div>
                <div className="card-label">
                  DATA INSPECTOR
                </div>

                <h2>
                  {viewer === "raw"
                    ? "Raw dataset"
                    : "Cleaned dataset"}
                </h2>

                <p>
                  {viewer === "raw"
                    ? "Exactly as uploaded."
                    : "Normalized representation used for inspection."}
                </p>
              </div>

              <button
                className="modal-close-button"
                onClick={() =>
                  setViewerOpen(false)
                }
              >
                ×
              </button>
            </div>

            {/* VIEW SWITCH */}

            <div className="viewer-tabs">
              <button
                className={
                  viewer === "raw"
                    ? "viewer-tab active"
                    : "viewer-tab"
                }
                onClick={() =>
                  changeViewer("raw")
                }
              >
                Raw Data
              </button>

              <button
                className={
                  viewer === "cleaned"
                    ? "viewer-tab active"
                    : "viewer-tab"
                }
                onClick={() =>
                  changeViewer("cleaned")
                }
              >
                Cleaned Data
              </button>
            </div>

            {/* CONTROLS */}

            <div className="viewer-toolbar">
              <input
                className="viewer-search"
                type="text"
                placeholder="Search the dataset..."
                value={viewerSearch}
                onChange={handleViewerSearch}
              />

              <select
                className="viewer-sort"
                value={viewerSort}
                onChange={handleSortChange}
              >
                <option value="">
                  Sort by...
                </option>

                {viewerColumns.map((column) => (
                  <option
                    value={column}
                    key={column}
                  >
                    {column}
                  </option>
                ))}
              </select>

              <button
                className="viewer-sort-button"
                onClick={toggleSortDirection}
                disabled={!viewerSort}
              >
                {viewerDescending
                  ? "↓ Descending"
                  : "↑ Ascending"}
              </button>
            </div>

            {/* TABLE */}

            <div className="viewer-info">
              <span>
                {viewerRows.length.toLocaleString()} rows
                shown
              </span>

              {viewer === "cleaned" && (
                <span className="cleaned-label">
                  CLEANED VIEW
                </span>
              )}
            </div>

            <div className="viewer-table-wrapper">
              {viewerLoading ? (
                <div className="viewer-loading">
                  <span className="button-spinner"></span>
                  Loading dataset...
                </div>
              ) : viewerRows.length === 0 ? (
                <div className="viewer-empty">
                  No rows match your search.
                </div>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th className="row-number">
                        #
                      </th>

                      {viewerColumns.map(
                        (column) => (
                          <th key={column}>
                            {column}
                          </th>
                        )
                      )}
                    </tr>
                  </thead>

                  <tbody>
                    {viewerRows.map(
                      (row, rowIndex) => (
                        <tr key={rowIndex}>
                          <td className="row-number">
                            {rowIndex + 1}
                          </td>

                          {viewerColumns.map(
                            (column) => (
                              <td
                                key={column}
                              >
                                {row[column] ===
                                  null ||
                                row[column] ===
                                  ""
                                  ? "—"
                                  : String(
                                      row[column]
                                    )}
                              </td>
                            )
                          )}
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;