import pandas as pd

from app.tools.file_access import resolve_user_document_path


ALLOWED_EXTENSIONS = {
    ".csv",
}


def analyze_csv(
    file_path: str,
) -> dict:

    try:
        path = resolve_user_document_path(file_path)
    except FileNotFoundError:
        return {
            "success": False,
            "error": "CSV file does not exist.",
        }
    except (PermissionError, ValueError):
        return {
            "success": False,
            "error": "CSV access is restricted to your documents.",
        }

    if path.suffix.lower() not in ALLOWED_EXTENSIONS:

        return {
            "success": False,
            "error": "Only CSV files are supported.",
        }

    try:

        dataframe = pd.read_csv(path)

        numeric_columns = (
            dataframe.select_dtypes(
                include="number"
            ).columns.tolist()
        )

        summary = {}

        if numeric_columns:

            statistics = (
                dataframe[numeric_columns]
                .describe()
                .round(3)
                .to_dict()
            )

            summary = statistics

        return {
            "success": True,
            "rows": len(dataframe),
            "columns": list(
                dataframe.columns
            ),
            "numeric_columns": numeric_columns,
            "missing_values": (
                dataframe.isnull()
                .sum()
                .to_dict()
            ),
            "statistics": summary,
        }

    except Exception as exc:

        return {
            "success": False,
            "error": f"CSV analysis failed: {exc}",
        }