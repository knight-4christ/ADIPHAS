"""
Shared download & copy utility for all AI-generated content across ADIPHAS.
Provides PDF export, Text export, and Copy-to-Clipboard functionality.
"""
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import io
import re


def _strip_markdown(text: str) -> str:
    """Strips markdown formatting for plain-text export."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)  # Italic
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'#{1,6}\s*', '', text)  # Headers
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)  # Links
    text = re.sub(r'---+', '─' * 40, text)  # Horizontal rules
    return text.strip()


def _generate_pdf_bytes(content: str, title: str = "ADIPHAS Intelligence Report") -> bytes:
    """Generates a PDF from text content using fpdf2."""
    try:
        from fpdf import FPDF
    except ImportError:
        return b""  # fpdf2 not installed — fallback handled by caller
    
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, title, ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", ln=True, align="C")
    pdf.cell(0, 6, "ADIPHAS - Autonomous Disease Intelligence Platform", ln=True, align="C")
    pdf.ln(5)
    
    # Divider
    pdf.set_draw_color(14, 165, 233)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(8)
    
    # Body content — handle markdown-like formatting
    plain_text = _strip_markdown(content)
    pdf.set_text_color(30, 30, 30)
    
    for line in plain_text.split("\n"):
        line = line.strip()
        if not line:
            pdf.ln(4)
            continue
        
        # Detect bullet points
        if line.startswith("- ") or line.startswith("• "):
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(8)  # Indent
            pdf.multi_cell(0, 6, f"• {line[2:]}")
        elif line.startswith("─"):
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(4)
        else:
            # Check if it looks like a heading (ALL CAPS or starts with emoji)
            if line.isupper() or (len(line) < 60 and line[0] not in "abcdefghijklmnopqrstuvwxyz"):
                pdf.set_font("Helvetica", "B", 11)
            else:
                pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, line)
    
    # Footer
    pdf.ln(10)
    pdf.set_draw_color(14, 165, 233)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 6, "ADIPHAS Critical Disclaimer: This is an advisory support tool and does not provide medical diagnoses.", ln=True, align="C")
    
    return pdf.output()


def _render_copy_button(content: str, key: str):
    """Renders a 'Copy to Clipboard' button using JavaScript."""
    # Escape content for JS embedding
    escaped = content.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")
    
    js_code = f"""
    <button onclick="copyToClipboard_{key}()" id="copy-btn-{key}" style="
        background: linear-gradient(135deg, #0ea5e9, #06b6d4);
        color: white;
        border: none;
        padding: 6px 16px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
        transition: all 0.2s ease;
    " onmouseover="this.style.transform='scale(1.03)'" onmouseout="this.style.transform='scale(1)'">
        📋 Copy to Clipboard
    </button>
    <script>
    function copyToClipboard_{key}() {{
        const text = `{escaped}`;
        navigator.clipboard.writeText(text).then(() => {{
            const btn = document.getElementById('copy-btn-{key}');
            btn.innerText = '✅ Copied!';
            btn.style.background = '#22c55e';
            setTimeout(() => {{
                btn.innerText = '📋 Copy to Clipboard';
                btn.style.background = 'linear-gradient(135deg, #0ea5e9, #06b6d4)';
            }}, 2000);
        }}).catch(() => {{
            const btn = document.getElementById('copy-btn-{key}');
            btn.innerText = '❌ Failed';
            setTimeout(() => {{ btn.innerText = '📋 Copy to Clipboard'; }}, 2000);
        }});
    }}
    </script>
    """
    components.html(js_code, height=45)


def render_download_buttons(content: str, filename_prefix: str = "adiphas_report", title: str = "ADIPHAS Intelligence Report", key_suffix: str = ""):
    """
    Renders a row of download (PDF, Text) and Copy buttons for any AI-generated content.
    
    Args:
        content: The text content to export
        filename_prefix: Base filename for downloads (timestamp auto-appended)
        title: Title for the PDF header
        key_suffix: Unique suffix for button keys to avoid duplicates
    """
    if not content:
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # PDF Download
        pdf_bytes = _generate_pdf_bytes(content, title=title)
        if pdf_bytes:
            st.download_button(
                "📄 Download PDF",
                data=pdf_bytes,
                file_name=f"{filename_prefix}_{timestamp}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"dl_pdf_{filename_prefix}_{key_suffix}"
            )
        else:
            st.caption("⚠️ PDF unavailable (install fpdf2)")
    
    with col2:
        # Text Download
        plain_text = _strip_markdown(content)
        full_text = f"{title}\nGenerated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n{'=' * 50}\n\n{plain_text}\n\n{'=' * 50}\nADIPHAS - Autonomous Disease Intelligence Platform\nDisclaimer: Advisory tool only. Consult a clinician for professional evaluation."
        
        st.download_button(
            "📝 Download Text",
            data=full_text,
            file_name=f"{filename_prefix}_{timestamp}.txt",
            mime="text/plain",
            use_container_width=True,
            key=f"dl_txt_{filename_prefix}_{key_suffix}"
        )
    
    with col3:
        _render_copy_button(content, key=f"cp_{filename_prefix}_{key_suffix}")
