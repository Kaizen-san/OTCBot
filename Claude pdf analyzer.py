import base64
import os
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT

# Replace with your actual API key
ANTHROPIC_API_KEY = "your_api_key_here"

def encode_pdf(file_path):
    with open(file_path, "rb") as pdf_file:
        return base64.b64encode(pdf_file.read()).decode('utf-8')

def analyze_with_claude(pdf_content):
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    
    questions = [
        "What is the main topic of this document?",
        "What are the key points discussed in this document?",
        "Are there any significant findings or conclusions presented?",
        "What is the overall tone or perspective of the document?",
        "Are there any recommendations or future actions suggested in the document?"
    ]
    
    analysis = "PDF Analysis:\n\n"
    
    initial_prompt = "I'm sending you a PDF document. Please analyze this document thoroughly. I will ask you specific questions about it afterwards."
    
    try:
        # Initial analysis
        response = client.completions.create(
            model="claude-2",
            max_tokens_to_sample=1000,
            prompt=f"{HUMAN_PROMPT}{initial_prompt}\n\n[PDF content (base64 encoded)]:\n{pdf_content}{AI_PROMPT}",
        )
        
        # Ask each question separately
        for question in questions:
            response = client.completions.create(
                model="claude-2",
                max_tokens_to_sample=1000,
                prompt=f"{HUMAN_PROMPT}{question}{AI_PROMPT}",
            )
            analysis += f"Q: {question}\nA: {response.completion}\n\n"
        
        return analysis
    except Exception as e:
        return f"An error occurred while analyzing the PDF with Claude: {str(e)}"

def main():
    pdf_path = input("Enter the path to your PDF file: ")
    
    if not os.path.exists(pdf_path):
        print("Error: The specified file does not exist.")
        return
    
    pdf_content = encode_pdf(pdf_path)
    analysis = analyze_with_claude(pdf_content)
    
    print(analysis)

if __name__ == "__main__":
    main()
