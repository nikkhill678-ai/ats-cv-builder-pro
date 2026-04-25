import streamlit as st
import PyPDF2
from docx import Document
import json
from fpdf import FPDF
from datetime import datetime

# ------------------- CONFIG -------------------
st.set_page_config(page_title="ATS CV Builder", layout="wide")
st.title("🎯 ATS-Friendly CV Builder + Score & Gap Analyzer")
st.markdown(
    "Paste a job description and upload your CV. "
    "Get a professional ATS score, see what’s missing, then generate a perfectly tailored CV."
)

# ------------------- HELPER FUNCTIONS -------------------
def extract_text_from_pdf(uploaded_file):
    reader = PyPDF2.PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

def extract_text_from_docx(uploaded_file):
    doc = Document(uploaded_file)
    return "\n".join([para.text for para in doc.paragraphs])

def call_gemini(prompt, api_key):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    # Updated to Gemini 2.5 Flash – the model you are using
    model = genai.GenerativeModel(
        'gemini-2.5-flash',
        generation_config={"response_mime_type": "application/json"}
    )
    response = model.generate_content(prompt)
    return response.text

def call_gpt(prompt, api_key, model_name):
    import openai
    openai.api_key = api_key
    response = openai.ChatCompletion.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a resume expert. Always respond with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=3000
    )
    return response.choices[0].message.content

def create_ats_pdf(cv_text, output_path="tailored_cv.pdf"):
    """
    Generate a plain‑text PDF that exactly mirrors the CV text.
    No bolding, no font changes – only words are added/removed.
    The bullet character is replaced with '-' to avoid font issues.
    """
    # Replace Unicode bullet with a safe ASCII hyphen
    sanitized = cv_text.replace('•', '-')
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)   # same font through‑out, no bold

    lines = sanitized.split('\n')
    for line in lines:
        # Keep the original spacing: empty lines become a small gap
        if not line.strip():
            pdf.ln(4)
            continue
        # Write the line as plain text, no indentation changes
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 5, line)

    pdf.output(output_path)
    return output_path

# ------------------- ATS ANALYSIS PROMPT (GOLD STANDARD, DATE‑AWARE) -------------------
def build_analysis_prompt(jd_text, cv_text):
    today_str = datetime.now().strftime("%B %d, %Y")
    return f"""
You are a dual expert: a certified ATS (Applicant Tracking System) architect AND a senior executive recruiter who has placed candidates at Fortune 100 companies.  
Your audit must be indistinguishable from a $1,000 professional CV review.

**TODAY'S DATE: {today_str}** — use this to judge whether dates in the CV are past, present, or future.  
Dates that are before today are valid past experience. Only flag dates that are genuinely in the future relative to today as an error.

## SCORING FRAMEWORK (6 dimensions, total 100 points)

| # | Dimension                        | Points | Exact Methodology |
|---|----------------------------------|--------|-------------------|
| 1 | Keyword Match & Semantic Density | 30     | Extract the **20 most critical hard skills, tools, certifications, and domain‑specific phrases** from the job description. For each, check if the CV contains an exact match OR a recognized synonym (e.g., "team leadership" ≈ "led a team of", "AWS" ≈ "Amazon Web Services"). Count matches: full match = 1 point, partial/synonym = 0.5 point. Score = (sum / 20) × 30. Deduct 2 points for each "must‑have" keyword completely absent. |
| 2 | ATS Parsability & Structure      | 20     | Check for: (a) standard section titles exactly: PROFESSIONAL SUMMARY, CORE COMPETENCIES or SKILLS, PROFESSIONAL EXPERIENCE, EDUCATION (missing each = -4 pts). (b) Absolutely **no** tables, columns, text boxes, headers/footers, graphics, or special icons (any infringement = -5 pts). (c) Consistent simple bullet points (•, -, *) throughout (inconsistent = -2 pts). |
| 3 | Quantification & Business Impact | 20     | Count total bullets in PROFESSIONAL EXPERIENCE. Count how many contain a **measurable result** (number, %, $, "increased by", "reduced by", "managed a team of X") OR a **clear scope descriptor** ("multiple", "end‑to‑end", "cross‑functional"). Score = (quantified bullets / total bullets) × 20. If no bullets exist, score = 0. |
| 4 | Action Verb Strength             | 10     | Check if ≥80% of experience bullets start with a strong, varied action verb (led, developed, implemented, designed, etc.). Passive phrasing ("Was responsible for") = weak verb. Score = (% strong verbs) × 10. |
| 5 | Role Alignment & Tailoring       | 10     | Does the PROFESSIONAL SUMMARY mention the exact job title or a very close equivalent? (3 pts). Are the top 3‑4 keywords from the JD placed prominently in the first half of the CV? (4 pts). Is the CV obviously generic (no mention of the industry’s tools or responsibilities)? (subtract up to 3 pts). |
| 6 | Professional Readability         | 10     | No first‑person pronouns (I, me, my) → -2 pts if present. No spelling/grammar errors → -2 per error. Bullets must be ≤2 lines and scannable (subjective: 0‑3 pts). Overall professional tone (subjective: 0‑3 pts). |

---

## CRITICAL AUDIT INSTRUCTIONS

1. **Calculate all scores mathematically** and show your work in the score_breakdown.  
2. **Derive `missing_keywords`**: list only JD keywords that are completely absent (no synonym found).  
3. **Derive `missing_skills_or_experience`**: identify experience areas, certifications, or qualifications the JD requires but the CV shows no evidence of. Be ruthlessly honest.  
4. **Derive `recommendations`**: based on the score breakdown, give **specific, actionable changes** in priority order.  
   - Each recommendation must reference the exact section or bullet to change.  
   - If a keyword is missing but the candidate likely has the skill, suggest adding it if truthful.  
   - If formatting is broken, tell exactly what to fix.  
   - If quantification is low, point to bullets that can be reworded.

---

## OUTPUT FORMAT (must be valid JSON, no extra text)

{{
  "overall_score": 72,
  "score_breakdown": "### ATS Score Breakdown\\n\\n| Dimension | Score | Max | Key Issue |\\n|---|---|---|---|\\n| Keyword Match | 22 | 30 | Missing 'CI/CD', 'Kubernetes' (hard req) |\\n| Formatting | 18 | 20 | Standard sections present, no tables |\\n| Quantification | 12 | 20 | Only 40% bullets have metrics |\\n| Action Verbs | 8 | 10 | 85% strong verbs, good |\\n| Tailoring | 7 | 10 | Summary lacks job title, generic skills |\\n| Readability | 5 | 10 | Several typos, one first‑person pronoun |\\n\\n**Total: 72/100**",
  "missing_keywords": ["CI/CD", "Kubernetes", "Financial modelling"],
  "missing_skills_or_experience": [
    "5+ years in financial services (required, but CV shows only tech experience)",
    "Certified Scrum Master (mentioned in JD but not in CV)"
  ],
  "recommendations": "1. Add 'CI/CD' and 'Kubernetes' to Skills section if truthful.\\n2. Rewrite the third bullet under Experience to include a metric (e.g., 'Improved deployment speed by implementing...').\\n3. Add a Professional Summary targeting the exact job title.\\n4. Fix spelling: 'managment' → 'management'.\\n5. Remove 'I was responsible for' and start with action verb."
}}

---
JOB DESCRIPTION:
{jd_text}

CANDIDATE CV:
{cv_text}

Return ONLY the JSON.
"""

# ------------------- CV GENERATION PROMPT (HEADINGS UNCHANGED, ARC STYLE) -------------------
def build_generation_prompt(jd_text, cv_text):
    today_str = datetime.now().strftime("%B %d, %Y")
    prompt = f"""
You are a senior recruitment consultant and ATS (Applicant Tracking System) engineer.  
Your dual task: rewrite a CV so it (a) passes ATS screens with a 90%+ match, and (b) looks professional and truthful to a human HR manager.

**TODAY'S DATE: {today_str}** — use this to verify that all experience dates are in the past or currently ongoing (e.g., “present”). Never flag past dates as future.

---

## NON‑NEGOTIABLE RULES

1. **DO NOT CHANGE ANY SECTION HEADINGS**  
   - Keep every section title exactly as it appears in the original CV. Do not add, remove, or rename any heading.  
   - Examples: if the original says "PROFILE SUMMARY", keep it that way. If it says "WORK EXPERIENCE", do not change it to "PROFESSIONAL EXPERIENCE".  
   - Your job is ONLY to improve the **content** under each heading.

2. **Truthfulness above all**  
   - Only use information that EXISTS in the original CV.  
   - Do NOT invent skills, qualifications, job titles, dates, or metrics.  
   - If the original CV doesn't mention a skill, do NOT add it — even if the job requires it. You may only rephrase and rearrange existing facts.

3. **Scannable bullet points (ARC approach)**  
   - Each bullet must follow the **Action → Result → Context** pattern where possible:  
     *Action*: strong verb (Led, Developed, Implemented…)  
     *Result*: measurable outcome or scope (e.g., “increased efficiency by 20%”, “managed a team of 5”)  
     *Context*: brief situation or tools used.  
   - Quantify achievements using numbers **only if they already appear** in the original CV. Otherwise use descriptive scope phrases like "managed multiple", "led cross‑functional teams", "handled end‑to‑end delivery".

4. **ATS keyword embedding**  
   - Extract EXACTLY 15-20 important keywords from the job description (hard skills, tools, certifications, methodologies).  
   - Embed these keywords naturally in the CV WHERE THEY TRUTHFULLY APPLY **without changing headings**.  
   - If the original CV already contains synonyms, replace them with the job description’s exact phrasing (e.g., if the JD says “Agile methodologies” and the CV says “Scrum”, use “Agile (Scrum)”).

5. **Formatting fidelity**  
   - Output plain text only – single column, no tables, no graphics.  
   - Use bullet points (•) for lists, but do **not** change the overall layout or headings.  
   - Keep contact details as they are; if they are missing, simply write `[Your Contact Info]`.

---

## YOUR OUTPUT TASKS

Based on the job description and the original CV provided below, you must:

A. **Rewrite the CV content** under each original heading. Follow all rules above. Return this as a string.

B. **Produce a detailed change log** — a list of bullet points explaining every modification you made and WHY (from an ATS/HR perspective).  
   - **Format requirement**: Each bullet must be on a **new line**, start with `• ` (bullet and space). Example:  
     `• Replaced ‘Scrum’ with ‘Agile (Scrum)’ because the job description repeatedly uses ‘Agile’.`  
     DO NOT run them together in one paragraph.

C. **Generate further improvement suggestions** — a list of 3-5 actionable tips the candidate could use to raise their ATS score even more, beyond what you were able to change. These should be specific and truthful.

Return your answer as a valid JSON object with EXACTLY three fields:  
- `"optimized_cv"`: the full rewritten CV (string).  
- `"changes"`: a string containing the change log (bullet points, each on a new line).  
- `"further_suggestions"`: a string containing the additional improvement tips (bullet points, each on a new line).

---

## JOB DESCRIPTION
---
{jd_text}
---

## ORIGINAL CV
---
{cv_text}
---

Return ONLY the JSON. No extra commentary, no markdown.
"""
    return prompt

# ------------------- SIDEBAR / MODEL SELECTION -------------------
st.sidebar.header("AI Engine Settings")
provider = st.sidebar.selectbox(
    "Choose AI provider:",
    ["Gemini 2.5 Flash (free)", "GPT-3.5 Turbo (paid)", "GPT-4o mini (paid)"]
)

api_key = None
gpt_model = "gpt-3.5-turbo"
if "Gemini" in provider:
    api_key = st.secrets.get("GEMINI_API_KEY") or st.sidebar.text_input("Gemini API Key", type="password")
else:
    api_key = st.secrets.get("OPENAI_API_KEY") or st.sidebar.text_input("OpenAI API Key", type="password")
    if "mini" in provider:
        gpt_model = "gpt-4o-mini"

# ------------------- MAIN INPUT AREA -------------------
col1, col2 = st.columns(2, gap="medium")
with col1:
    st.subheader("📋 Job Description")
    jd_text = st.text_area("Paste the full job description here:", height=300)
    jd_file = st.file_uploader("Or upload a .txt file", type="txt", key="jd")
    if jd_file:
        jd_text = jd_file.read().decode("utf-8")
        st.success("Job description loaded!")

with col2:
    st.subheader("📄 Your Current CV")
    cv_file = st.file_uploader("Upload CV (PDF or DOCX)", type=["pdf", "docx"])
    cv_text = ""
    if cv_file is not None:
        file_type = cv_file.type
        try:
            if file_type == "application/pdf":
                cv_text = extract_text_from_pdf(cv_file)
            else:
                cv_text = extract_text_from_docx(cv_file)
            if cv_text.strip() == "":
                st.warning("Could not extract text. It might be an image/scanned file.")
            else:
                st.success("CV text extracted!")
                with st.expander("👀 Preview extracted text", expanded=False):
                    st.text_area("Full CV text (scrollable)", value=cv_text, height=300)
        except Exception as e:
            st.error(f"Error reading file: {e}")

# ------------------- ACTION BUTTONS -------------------
st.divider()
col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    analyze_clicked = st.button("📊 Analyse Current CV (ATS Score & Gaps)", type="secondary", use_container_width=True)
with col_btn2:
    generate_clicked = st.button("✨ Generate ATS-Optimized CV", type="primary", use_container_width=True)

# ------------------- ANALYSIS LOGIC -------------------
if analyze_clicked:
    if not api_key:
        st.error("Please enter an API key in the sidebar.")
    elif not jd_text.strip():
        st.warning("Please provide a job description.")
    elif not cv_text or len(cv_text.strip()) < 20:
        st.warning("Please upload a valid CV with enough text.")
    else:
        prompt = build_analysis_prompt(jd_text, cv_text)
        with st.spinner("🔍 Analysing CV against job description..."):
            try:
                if "Gemini" in provider:
                    raw_response = call_gemini(prompt, api_key)
                else:
                    raw_response = call_gpt(prompt, api_key, gpt_model)

                result = json.loads(raw_response)
                st.session_state["analysis"] = result
                st.success("Analysis complete! Results below.")
            except json.JSONDecodeError:
                st.error("The AI did not return valid JSON. Raw response:")
                st.code(raw_response if 'raw_response' in locals() else "")
            except Exception as e:
                st.error(f"An error occurred: {e}")

# ------------------- GENERATION LOGIC -------------------
if generate_clicked:
    if not api_key:
        st.error("Please enter an API key in the sidebar.")
    elif not jd_text.strip():
        st.warning("Please provide a job description.")
    elif not cv_text or len(cv_text.strip()) < 20:
        st.warning("Please upload a valid CV with enough text.")
    else:
        prompt = build_generation_prompt(jd_text, cv_text)
        with st.spinner("✨ Tailoring your CV..."):
            try:
                if "Gemini" in provider:
                    raw_response = call_gemini(prompt, api_key)
                else:
                    raw_response = call_gpt(prompt, api_key, gpt_model)

                result = json.loads(raw_response)
                st.session_state["optimized_cv"] = result["optimized_cv"]
                st.session_state["changes"] = result["changes"]
                st.session_state["further_suggestions"] = result.get("further_suggestions", "No further suggestions.")
                st.success("Tailored CV generated! Results below.")
            except json.JSONDecodeError:
                st.error("AI did not return valid JSON. Raw response:")
                st.code(raw_response if 'raw_response' in locals() else "")
            except Exception as e:
                st.error(f"An error occurred: {e}")

# ------------------- DISPLAY ANALYSIS RESULTS -------------------
if "analysis" in st.session_state:
    data = st.session_state["analysis"]
    st.divider()
    st.subheader("📊 ATS Audit Report")

    score = data.get("overall_score", 0)
    col_score1, col_score2 = st.columns([1, 3])
    with col_score1:
        st.metric("Overall ATS Score", f"{score}/100")
    with col_score2:
        st.progress(score / 100)

    tab1, tab2, tab3 = st.tabs(["🔎 Score Breakdown", "❌ Missing Keywords & Skills", "💡 Recommendations"])
    with tab1:
        st.markdown(data.get("score_breakdown", "No breakdown provided."))
    with tab2:
        missing_kw = data.get("missing_keywords", [])
        missing_skills = data.get("missing_skills_or_experience", [])
        if missing_kw:
            st.markdown("**Missing Keywords (from JD):**")
            for kw in missing_kw:
                st.markdown(f"- {kw}")
        else:
            st.success("All important keywords appear to be present!")
        if missing_skills:
            st.markdown("**Skills / Experience Gaps:**")
            for item in missing_skills:
                st.markdown(f"- {item}")
        else:
            st.success("No obvious skill gaps detected.")
    with tab3:
        recs = data.get("recommendations", "No specific recommendations.")
        if isinstance(recs, list):
            for r in recs:
                st.markdown(f"- {r}")
        else:
            st.markdown(recs)

# ------------------- DISPLAY GENERATION RESULTS -------------------
if "optimized_cv" in st.session_state:
    st.divider()
    tab_cv, tab_changes, tab_suggestions = st.tabs(["📝 New ATS CV", "🔍 What Changed", "💡 Further Improvement Tips"])

    with tab_cv:
        st.subheader("Your Optimised CV")
        edited = st.text_area(
            "Copy, edit, or refine:",
            value=st.session_state["optimized_cv"],
            height=400,
            key="edit_cv"
        )
        if edited != st.session_state["optimized_cv"]:
            st.session_state["optimized_cv"] = edited

        col_dl1, col_dl2, col_dl3 = st.columns([1,1,2])
        with col_dl1:
            st.download_button(
                "⬇️ Download TXT",
                data=st.session_state["optimized_cv"],
                file_name="tailored_cv.txt",
                mime="text/plain"
            )
        with col_dl2:
            if st.button("📄 Generate PDF", key="pdf_btn"):
                with st.spinner("Creating PDF..."):
                    pdf_path = create_ats_pdf(st.session_state["optimized_cv"])
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()
                    st.download_button(
                        "⬇️ Download PDF",
                        data=pdf_bytes,
                        file_name="tailored_cv.pdf",
                        mime="application/pdf",
                        key="pdf_dl"
                    )
        with col_dl3:
            if st.button("🔁 Re‑Score This Tailored CV", key="rescore"):
                with st.spinner("Scoring tailored CV..."):
                    prompt = build_analysis_prompt(jd_text, edited)
                    try:
                        if "Gemini" in provider:
                            raw = call_gemini(prompt, api_key)
                        else:
                            raw = call_gpt(prompt, api_key, gpt_model)
                        new_analysis = json.loads(raw)
                        st.session_state["analysis"] = new_analysis
                        st.success("Re‑scored! Scroll up to see the new report.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Re‑scoring failed: {e}")

    with tab_changes:
        st.subheader("Detailed Change Log")
        st.markdown(st.session_state["changes"])

    with tab_suggestions:
        st.subheader("What else could improve your CV?")
        st.markdown(st.session_state["further_suggestions"])
