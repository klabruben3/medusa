"""Document utilities. Imports stay lazy so unused embedding clients need no keys."""


def extract_document_info(uploaded_file):
    from .upload import extract_document_info as extract
    return extract(uploaded_file)
