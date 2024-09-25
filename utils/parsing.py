import re
import logging

logger = logging.getLogger(__name__)

def parse_claude_response(response):
    # Try to extract the text between [TextBlock(text='...')]
    match = re.search(r"\[TextBlock\(text='(.*?)', type='text'\)\]", response, re.DOTALL)
    
    if match:
        logger.info("Using regex-based parsing for response.")
        text = match.group(1)
    else:
        logger.info("Using plain-text parsing for response.")
        # If no match, assume the response is plain text
        text = response

    # Replace "\\n\\n" with a custom paragraph separator
    text = text.replace("\\n\\n", "\n\n<PARAGRAPH>\n\n")
    
    # Replace "\\n" with actual newlines
    text = text.replace("\\n", "\n")
    
    # Split into paragraphs and join with double newlines
    paragraphs = text.split("<PARAGRAPH>")
    formatted_text = "\n\n".join(paragraph.strip() for paragraph in paragraphs)
    
    # Debug log at the end of the function
    logger.debug(f"Formatted response: {formatted_text[:500]}...")  # Log first 500 characters
    
    return formatted_text