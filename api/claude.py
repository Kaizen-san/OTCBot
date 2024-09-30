import logging
from anthropic import AsyncAnthropic, Anthropic
from config import Config

logger = logging.getLogger(__name__)

async def analyze_with_claude(ticker, text_content, previous_close_price):
    logger.debug(f"Starting analysis with Claude for ticker: {ticker}")
    
    questions = [
        "In what industry is it? (Block chain, real estate, mining, etc..)",
        "Is it a shell company? If yes, what are the plans for this shell?",
        "What is the amount of the convertible notes the company has? (in $)",
        "When are the convertible notes due? Please elaborate on each convertible note mentioned in the document, including its due date",
        "Have there been any changes to the share structure between the quarters, such as share dilution or a decrease in the number of shares?",
        "Did they settle them (the convertible notes) or do they have plans to settle or do something with it?",
        "Are there any future plans for the business?",
        "Are there any upcoming material events disclosed or hinted at in the document, such as potential acquisitions, mergers, or significant changes in the share structure?",
        "Are there any plans for reverse split in the future?",
        f"What is the ratio of total assets to market capitalization (total market cap) for the company, based on the information provided in the document? Use the previous close price of ${previous_close_price} to calculate the market cap.",
    ]
    
    prompt = f"""Analyze the following document thoroughly for {ticker}, including any tables or structured data. Then answer these questions:

{chr(10).join(f"{i+1}. {q}" for i, q in enumerate(questions))}

Document content:
{text_content[:100000]}  # Limit to first 100,000 characters to avoid token limits

Start your reply with "Here is the analysis for {ticker}:" Provide your answers in a clear, concise manner but not as you are answering a question but as if you are stating a fact. Do not include question numbers or prefixes in your responses.
"""

    try:
        async with AsyncAnthropic(api_key=Config.ANTHROPIC_API_KEY) as client:
            response = await client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=4000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
        
        logger.debug(f"Raw response from Claude: {response}")
        
        if hasattr(response, 'content') and isinstance(response.content, list):
            for content_item in response.content:
                if hasattr(content_item, 'text'):
                    logger.info(f"Successfully parsed Claude API response for {ticker}")
                    return content_item.text
        
        logger.error(f"Unexpected response format from Claude API: {response}")
        return None

    except Exception as e:
        logger.exception(f"Error calling Claude API for {ticker}: {str(e)}")
        return None