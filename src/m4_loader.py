# src/m4_loader.py
"""
Utilities to download, extract and work with the M4 dataset from the
M4comp2018 R package.

Design goals:
- Keep the original M4 object in R (lazy loading, factors, etc.).
- Use rpy2 only as a thin bridge to R.
- Expose simple Python helpers for:
    - downloading the R package tarball,
    - extracting M4.rda,
    - loading the M4 object into an R session,
    - inspecting individual series,
    - filtering series by period and type (using factor codes).
"""

import tarfile
import urllib.request
from pathlib import Path

import numpy as np
from rpy2.robjects import r, globalenv

from config import M4_TARBALL_URL, M4_TARBALL_PATH, RDA_PATH, DATA_DIR


# ---------------------------------------------------------------------------
# R factor level mappings (documented from M4comp2018)
# ---------------------------------------------------------------------------

# These mappings reflect the factor levels in the original R M4 object.
# In R:
#   levels(M4[[1]]$period) -> "Daily" "Hourly" "Monthly" "Quarterly" "Weekly "Yearly"
#   levels(M4[[1]]$type)   -> "Demographic" "Finance" "Industry" "Macro" "Micro" "Other"

PERIOD_LABEL_TO_CODE = {
    "Daily": "1",
    "Hourly": "2",
    "Monthly": "3",
    "Quarterly": "4",
    "Weekly": "5",
    "Yearly": "6",
}

TYPE_LABEL_TO_CODE = {
    "Demographic": "1",
    "Finance": "2",
    "Industry": "3",
    "Macro": "4",
    "Micro": "5",
    "Other": "6",
}


def get_m4_factor_codes(m4_r_object, index: int) -> tuple[str, str]:
    """
    Return the factor codes for 'period' and 'type' of a given M4 series.

    Parameters
    ----------
    m4_r_object : rpy2 ListVector
        The M4 object as loaded from M4.rda (via load_m4_r_object()).
    index : int
        1-based index of the series (R-style), i.e. index=1 corresponds to M4[[1]].

    Returns
    -------
    (str, str)
        Tuple (period_code, type_code), both as strings '1'..'6'.

        These codes correspond to the R factor levels documented above, e.g.:
        period_code '4' -> "Quarterly"
        type_code   '2' -> "Finance"
    """
    s = m4_r_object.rx2(index)
    period_code = str(s.rx2("period")[0])  # factor code as string '1'..'6'
    type_code = str(s.rx2("type")[0])      # factor code as string '1'..'6'
    return period_code, type_code


# ---------------------------------------------------------------------------
# Download and extract M4.rda from the M4comp2018 tarball
# ---------------------------------------------------------------------------

def download_m4_tarball(force: bool = False) -> Path:
    """
    Download the M4comp2018 source tarball into DATA_DIR.

    This fetches the R package tar.gz from GitHub and stores it at
    M4_TARBALL_PATH, unless it already exists and force=False.

    Parameters
    ----------
    force : bool, optional
        If True, re-download the tarball even if it already exists.

    Returns
    -------
    Path
        Path to the downloaded tarball (M4_TARBALL_PATH).
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if M4_TARBALL_PATH.exists() and not force:
        print(f"Tarball already exists at: {M4_TARBALL_PATH}")
        return M4_TARBALL_PATH

    print(f"Downloading M4comp2018 tarball from:\n  {M4_TARBALL_URL}")
    urllib.request.urlretrieve(M4_TARBALL_URL, M4_TARBALL_PATH)
    print(f"Saved to: {M4_TARBALL_PATH}")
    return M4_TARBALL_PATH


def extract_m4_rda_from_tarball(
    tar_path: Path | None = None,
    force: bool = False
) -> Path:
    """
    Extract the M4 dataset file (M4.rda / M4.RData) from the tarball.

    The function searches inside the R package tar.gz for:
        * M4comp2018/data/M4.rda   or
        * M4comp2018/data/M4.RData

    and writes it as DATA_DIR / "M4.rda".

    Parameters
    ----------
    tar_path : Path or None, optional
        Path to the tar.gz file. If None, uses M4_TARBALL_PATH.
    force : bool, optional
        If True, overwrite an existing M4.rda.

    Returns
    -------
    Path
        Path to the extracted RDA file (RDA_PATH).
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if tar_path is None:
        tar_path = M4_TARBALL_PATH

    if not tar_path.exists():
        raise FileNotFoundError(f"Tarball not found at: {tar_path}")

    if RDA_PATH.exists() and not force:
        print(f"M4.rda already exists at: {RDA_PATH}")
        return RDA_PATH

    print(f"Extracting M4.* from tarball: {tar_path}")

    with tarfile.open(tar_path, "r:gz") as tar:
        member_to_extract = None
        for member in tar.getmembers():
            # Package data is usually under "M4comp2018/data/M4.rda" or "M4.RData"
            name = member.name.lower()
            if name.endswith("/data/m4.rda") or name.endswith("/data/m4.rdata"):
                member_to_extract = member
                break

        if member_to_extract is None:
            raise FileNotFoundError(
                "Could not find M4.rda or M4.RData inside the tarball."
            )

        extracted_file = tar.extractfile(member_to_extract)
        if extracted_file is None:
            raise RuntimeError("Failed to extract M4 data file from tarball.")

        with open(RDA_PATH, "wb") as f_out:
            f_out.write(extracted_file.read())

    print(f"Extracted {member_to_extract.name} -> {RDA_PATH}")
    return RDA_PATH


# ---------------------------------------------------------------------------
# R bridge: load and inspect the M4 object
# ---------------------------------------------------------------------------

def load_m4_r_object(rda_path: Path | None = None):
    """
    Load the M4 object from an RDA file using R (via rpy2).

    This calls R's load() on the given RDA file (default: config.RDA_PATH),
    and returns the object named "M4" from the R global environment.

    Parameters
    ----------
    rda_path : Path or None, optional
        Path to the M4.rda file. If None, uses config.RDA_PATH.

    Returns
    -------
    rpy2.robjects.vectors.ListVector
        The M4 object as an R list-of-lists, identical to the R M4 object.

    Notes
    -----
    - The function does not materialise or copy the dataset in Python.
      The structure remains primarily in R, accessed lazily through rpy2.
    - This mirrors the behaviour of:
        library(M4comp2018)
        data(M4)
    """
    if rda_path is None:
        rda_path = RDA_PATH

    rda_path = Path(rda_path).resolve()
    if not rda_path.exists():
        raise FileNotFoundError(f"M4.rda not found at: {rda_path}")

    print(f"Loading M4 from: {rda_path}")

    # Clear any previous M4 in R global env
    if "M4" in globalenv:
        del globalenv["M4"]

    r(f'load("{rda_path.as_posix()}")')

    if "M4" not in globalenv:
        raise RuntimeError(
            f'"M4" not found in R global environment after loading {rda_path}.'
        )

    m4 = globalenv["M4"]
    print(f"Retrieved M4 object from R. Total series: {len(m4)}")
    return m4


def get_m4_series_py(m4_r_object, index: int) -> dict:
    """
    Extract a single M4 series and convert key fields to Python types.

    This is a simple helper that returns a subset of fields
    useful for quick inspection or experiments.

    Parameters
    ----------
    m4_r_object : rpy2 ListVector
        The M4 object as returned by load_m4_r_object().
    index : int
        1-based index of the series (R-style).

    Returns
    -------
    dict
        Dictionary with keys:
            'st'     : series identifier (str)
            'n'      : length of historical data (int)
            'h'      : forecast horizon (int)
            'period' : factor code as string '1'..'6'
            'type'   : factor code as string '1'..'6'
            'x'      : numpy array of historical values
            'xx'     : numpy array of future values (true values on horizon)
    """
    s = m4_r_object.rx2(index)  # R-style [[index]]

    out = {
        "st": str(s.rx2("st")[0]),
        "n": int(s.rx2("n")[0]),
        "h": int(s.rx2("h")[0]),
        "period": str(s.rx2("period")[0]),  # factor code
        "type": str(s.rx2("type")[0]),      # factor code
        "x": np.array(s.rx2("x"), dtype=float),
        "xx": np.array(s.rx2("xx"), dtype=float),
    }
    return out


def print_m4_variables(m4_r_object, index: int) -> None:
    """
    Print the field names for a given M4 series, mirroring names(M4[[i]]) in R.

    Parameters
    ----------
    m4_r_object : rpy2 ListVector
        The M4 object as returned by load_m4_r_object().
    index : int
        1-based index of the series.
    """
    series = m4_r_object.rx2(index)
    variables = list(series.names)
    print(f"Variables for M4[[{index}]]:")
    for v in variables:
        print(" -", v)


# ---------------------------------------------------------------------------
# Higher-level helpers: full series extraction and filtering
# ---------------------------------------------------------------------------

def extract_m4_series(m4_r_object, index: int) -> dict:
    """
    Extract all standard M4 fields for one series into a Python dict.

    The result mirrors the structure of a single M4[[i]] element, with
    numeric vectors converted to numpy arrays and scalar values converted
    to Python scalars.

    Parameters
    ----------
    m4_r_object : rpy2 ListVector
        The M4 object as returned by load_m4_r_object().
    index : int
        1-based index of the series.

    Returns
    -------
    dict
        Dictionary with keys:
            'st', 'x', 'n', 'type', 'h', 'period', 'xx',
            'pt_ff', 'up_ff', 'low_ff'.

        'period' and 'type' are kept as factor codes (strings '1'..'6').
        They can be mapped back to labels using the dictionaries:
            PERIOD_LABEL_TO_CODE / TYPE_LABEL_TO_CODE
            and their inverses if needed.
    """
    s = m4_r_object.rx2(index)
    names = list(s.names)

    out: dict[str, object] = {}

    for name in names:
        value = s.rx2(name)

        if name in ["x", "xx", "pt_ff", "up_ff", "low_ff"]:
            out[name] = np.array(value, dtype=float)

        elif name in ["st"]:
            out[name] = str(value[0])

        elif name in ["period", "type"]:
            # Keep factor codes as strings, e.g. '4', '3'
            out[name] = str(value[0])

        elif name in ["n", "h"]:
            out[name] = int(value[0])

        else:
            # For any unexpected field, return the raw rpy2 object.
            out[name] = value

    return out


def filter_m4_series(
    m4_r_object,
    period: str | None = None,
    type: str | None = None,
    max_series: int | None = None,
) -> dict[int, dict]:
    """
    Filter M4 series by 'period' and 'type' labels, using factor codes internally.

    Parameters
    ----------
    m4_r_object : rpy2 ListVector
        The M4 object as returned by load_m4_r_object().
    period : str or None, optional
        M4 period label, e.g. "Yearly", "Quarterly", "Monthly", etc.
        If None, no filter is applied on period.
    type : str or None, optional
        M4 type label, e.g. "Finance", "Macro", "Industry", etc.
        If None, no filter is applied on type.
    max_series : int or None, optional
        Optional cap on number of series to extract. Useful for tests.

    Returns
    -------
    dict[int, dict]
        Dictionary mapping series index (1-based, as in R: M4[[index]])
        to the extracted series dict (as returned by extract_m4_series()).

    Notes
    -----
    - Users pass human-readable labels (e.g. period="Quarterly", type="Finance").
    - Internally, these labels are mapped to factor codes ('1'..'6') via
      PERIOD_LABEL_TO_CODE and TYPE_LABEL_TO_CODE, and we compare against
      the factor codes stored in the R object.
    - This keeps the R M4 object as the main data store and only extracts
      matching series into Python.
    """
    # Convert labels -> codes
    period_code = PERIOD_LABEL_TO_CODE.get(period) if period else None
    type_code = TYPE_LABEL_TO_CODE.get(type) if type else None

    n_total = len(m4_r_object)
    results: dict[int, dict] = {}
    count = 0

    for idx in range(1, n_total + 1):
        p_code, t_code = get_m4_factor_codes(m4_r_object, idx)

        if period_code and p_code != period_code:
            continue
        if type_code and t_code != type_code:
            continue

        # Only extract full series once matched
        results[idx] = extract_m4_series(m4_r_object, idx)
        count += 1

        if max_series and count >= max_series:
            break

    print(
        f"Selected {len(results)} series out of {n_total} "
        f"(period={period}, type={type})"
    )
    return results
