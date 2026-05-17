#!/usr/bin/env python3
"""
Debug script to test PDF parsing for oncology protocols
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

def debug_pdf(pdf_path: str):
    """Debug PDF parsing step by step"""
    
    print("=" * 60)
    print("PDF PARSING DEBUG")
    print("=" * 60)
    
    # Step 1: Check if file exists
    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        return
    
    print(f"\n1. FILE INFO:")
    print(f"   Path: {pdf_path}")
    print(f"   Size: {os.path.getsize(pdf_path):,} bytes")
    
    # Step 2: Extract text from PDF
    print(f"\n2. TEXT EXTRACTION:")
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        print(f"   Pages: {len(doc)}")
        
        full_text = ""
        for page_num in range(min(len(doc), 5)):  # First 5 pages
            page = doc[page_num]
            text = page.get_text()
            full_text += text
            print(f"   Page {page_num + 1}: {len(text)} chars")
        
        doc.close()
        
        print(f"\n   Total text extracted: {len(full_text):,} chars")
        print(f"\n   FIRST 2000 CHARS OF EXTRACTED TEXT:")
        print("-" * 40)
        print(full_text[:2000])
        print("-" * 40)
        
    except Exception as e:
        print(f"   ERROR extracting text: {e}")
        return
    
    # Step 3: Parse with LLM
    print(f"\n3. LLM PARSING:")
    try:
        from src.protocol_intelligence.oncology_parser import OncologyProtocolParser
        
        parser = OncologyProtocolParser()
        print("   Parser initialized")
        
        # Parse the PDF
        print("   Sending to LLM for parsing...")
        protocol = parser.parse_pdf(pdf_path)
        
        print(f"\n   PARSED RESULTS:")
        print(f"   - Title: {protocol.metadata.trial_title or 'NOT FOUND'}")
        print(f"   - Protocol #: {protocol.metadata.protocol_number or 'NOT FOUND'}")
        print(f"   - Sponsor: {protocol.metadata.sponsor or 'NOT FOUND'}")
        print(f"   - Phase: {protocol.metadata.phase or 'NOT FOUND'}")
        print(f"   - Cancer Type: {protocol.indication.cancer_type or 'NOT FOUND'}")
        print(f"   - Cancer Subtype: {protocol.indication.cancer_subtype or 'NOT FOUND'}")
        print(f"   - Intervention: {protocol.intervention.intervention_type or 'NOT FOUND'}")
        print(f"   - Drug Name: {protocol.intervention.drug_name or 'NOT FOUND'}")
        print(f"   - Line of Therapy: {protocol.population.line_of_therapy or 'NOT FOUND'}")
        print(f"   - Biomarkers: {protocol.population.biomarker_requirements or 'NOT FOUND'}")
        print(f"   - Primary Endpoint: {protocol.endpoints.primary_endpoint or 'NOT FOUND'}")
        print(f"   - Target Enrollment: {protocol.design.target_enrollment or 'NOT FOUND'}")
        print(f"   - Parsing Confidence: {protocol.parsing_confidence}")
        print(f"   - Parsing Notes: {protocol.parsing_notes}")
        
    except Exception as e:
        import traceback
        print(f"   ERROR during LLM parsing: {e}")
        traceback.print_exc()
        return
    
    # Step 4: Score the protocol
    print(f"\n4. SCORING:")
    try:
        from src.protocol_intelligence.oncology_scoring import OncologyProtocolScorer
        
        scorer = OncologyProtocolScorer()
        scores = scorer.score_protocol(protocol)
        
        print(f"   - Overall Complexity: {scores.overall_complexity}")
        print(f"   - Enrollment Difficulty: {scores.enrollment_difficulty.score}")
        print(f"   - Site Burden: {scores.site_burden.score}")
        print(f"   - Risk Flags: {len(scores.risk_flags)}")
        for rf in scores.risk_flags:
            print(f"     * [{rf.severity.upper()}] {rf.flag_name}")
        
    except Exception as e:
        import traceback
        print(f"   ERROR during scoring: {e}")
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("DEBUG COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_pdf_parsing.py <path_to_pdf>")
        print("\nExample: python debug_pdf_parsing.py /path/to/protocol.pdf")
        sys.exit(1)
    
    debug_pdf(sys.argv[1])
