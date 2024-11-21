import PyPDF2
import io
import logging

"""
PDF processing utilities module.
Provides functionality for extracting text content from PDF files,
particularly for financial reports and documents.

"""


logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_content):
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        if not text.strip():
            logger.warning("Extracted text is empty")
            return None
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return None