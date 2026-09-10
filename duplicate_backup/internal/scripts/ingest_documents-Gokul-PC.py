from app.config.settings import DOCUMENTS_DIR
from app.tools.rag import ingest_document


def main():

    documents = [
        path
        for path in DOCUMENTS_DIR.iterdir()
        if path.is_file()
    ]

    if not documents:

        print(
            "No documents found in "
            f"{DOCUMENTS_DIR}"
        )

        return

    for document in documents:

        print(
            f"\nProcessing: {document.name}"
        )

        result = ingest_document(
            str(document)
        )

        print(result)


if __name__ == "__main__":
    main()