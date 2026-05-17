# Protocol Intelligence System Design

## Overview

Protocol Intelligence analyzes clinical trial protocols to predict operational complexity and recommend optimal PI/site matches.

**Positioning**: "Operational intelligence for protocol execution" (NOT "AI protocol writer")

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     PROTOCOL INTELLIGENCE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │   INPUTS     │────▶│   PARSER     │────▶│  STRUCTURED  │    │
│  │              │     │              │     │    JSON      │    │
│  │ • Protocol   │     │ • PDF/Text   │     │              │    │
│  │   PDF        │     │   extraction │     │ • indication │    │
│  │ • Structured │     │ • LLM-based  │     │ • criteria   │    │
│  │   overrides  │     │   parsing    │     │ • endpoints  │    │
│  └──────────────┘     └──────────────┘     │ • schedule   │    │
│                                            └───────┬──────┘    │
│                                                    │           │
│                                                    ▼           │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │   OUTPUTS    │◀────│   MATCHER    │◀────│   SCORING    │    │
│  │              │     │              │     │   ENGINE     │    │
│  │ • Risk       │     │ • Site       │     │              │    │
│  │   summary    │     │   profiles   │     │ • Enrollment │    │
│  │ • Scores     │     │ • PI         │     │ • Site burden│    │
│  │ • Recs       │     │   profiles   │     │ • Complexity │    │
│  └──────────────┘     └──────────────┘     └──────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Data Schema

### Protocol Input (Structured JSON)

```json
{
  "protocol_id": "PROTO-2024-001",
  "title": "Phase II Study of XYZ-123 in Type 2 Diabetes",
  
  "basic_info": {
    "indication": "Type 2 Diabetes",
    "phase": "Phase II",
    "study_type": "Interventional",
    "target_enrollment": 250,
    "study_duration_months": 18,
    "number_of_sites": 25,
    "geography": ["United States", "Canada", "Germany"]
  },
  
  "eligibility": {
    "inclusion_criteria": [
      "Adults aged 18-75 years",
      "Diagnosed with T2DM for ≥6 months",
      "HbA1c 7.0-10.0%",
      "BMI 25-40 kg/m²",
      "Stable metformin dose for ≥3 months"
    ],
    "exclusion_criteria": [
      "Type 1 diabetes",
      "eGFR <45 mL/min/1.73m²",
      "History of pancreatitis",
      "Current insulin use",
      "Pregnancy or breastfeeding"
    ],
    "target_population": {
      "age_range": [18, 75],
      "pediatric": false,
      "rare_disease": false,
      "biomarker_required": true,
      "biomarker_details": "HbA1c 7.0-10.0%",
      "washout_required": false
    }
  },
  
  "endpoints": {
    "primary": {
      "name": "Change in HbA1c from baseline at Week 24",
      "type": "efficacy",
      "measurement": "laboratory"
    },
    "secondary": [
      {"name": "Fasting plasma glucose", "type": "efficacy"},
      {"name": "Body weight change", "type": "efficacy"},
      {"name": "Time in range (CGM)", "type": "efficacy"}
    ],
    "safety": [
      "Adverse events",
      "Hypoglycemia episodes",
      "Vital signs"
    ]
  },
  
  "schedule_of_activities": {
    "total_visits": 12,
    "visit_frequency": "every 2 weeks for 8 weeks, then monthly",
    "study_duration_weeks": 24,
    "screening_period_weeks": 2,
    "follow_up_weeks": 4,
    "overnight_stays": 0,
    "home_visits": 0
  },
  
  "assessments": {
    "laboratory": {
      "frequency": "every visit",
      "special_labs": ["HbA1c", "lipid panel", "liver function"],
      "central_lab_required": true
    },
    "imaging": {
      "required": false,
      "types": [],
      "frequency": null
    },
    "devices": {
      "required": true,
      "types": ["continuous glucose monitor"],
      "training_required": true
    },
    "patient_reported_outcomes": {
      "required": true,
      "questionnaires": ["DTSQ", "EQ-5D"]
    }
  },
  
  "safety_monitoring": {
    "dsmb_required": true,
    "interim_analyses": 1,
    "stopping_rules": true,
    "special_monitoring": ["hepatic function", "hypoglycemia"]
  },
  
  "intervention": {
    "type": "drug",
    "route": "oral",
    "dosing_frequency": "once daily",
    "dose_modifications": true,
    "comparator": "placebo",
    "blinding": "double-blind"
  },
  
  "sponsor_preferences": {
    "site_type": "mixed",  // academic, community, mixed
    "experience_priority": "high",
    "geographic_diversity": true,
    "enrollment_speed_priority": "medium"
  }
}
```

## Scoring Engine

### 1. Enrollment Difficulty Score (0-100)

Factors:
- **Criteria stringency** (narrow age, biomarkers, washouts)
- **Population rarity** (rare disease, pediatric, specific genotypes)
- **Competition** (similar active trials in same indication)
- **Geographic constraints**
- **Screening failure prediction**

```python
def calculate_enrollment_difficulty(protocol):
    score = 0
    
    # Criteria complexity
    inclusion_count = len(protocol.eligibility.inclusion_criteria)
    exclusion_count = len(protocol.eligibility.exclusion_criteria)
    score += min(30, (inclusion_count + exclusion_count) * 2)
    
    # Population factors
    if protocol.eligibility.target_population.rare_disease:
        score += 25
    if protocol.eligibility.target_population.pediatric:
        score += 15
    if protocol.eligibility.target_population.biomarker_required:
        score += 10
    if protocol.eligibility.target_population.washout_required:
        score += 10
    
    # Age range narrowness
    age_range = protocol.eligibility.target_population.age_range
    if age_range[1] - age_range[0] < 20:
        score += 15
    
    return min(100, score)
```

### 2. Site Burden Score (0-100)

Factors:
- **Visit frequency**
- **Assessment complexity** (imaging, special labs, devices)
- **Staff training requirements**
- **Equipment requirements**
- **Documentation burden**

```python
def calculate_site_burden(protocol):
    score = 0
    
    # Visit burden
    visits_per_month = protocol.schedule.total_visits / (protocol.schedule.study_duration_weeks / 4)
    score += min(25, visits_per_month * 5)
    
    # Assessment burden
    if protocol.assessments.imaging.required:
        score += 20
    if protocol.assessments.devices.required:
        score += 15
    if protocol.assessments.devices.training_required:
        score += 10
    if protocol.assessments.laboratory.central_lab_required:
        score += 5
    
    # Overnight stays
    score += protocol.schedule.overnight_stays * 10
    
    return min(100, score)
```

### 3. Operational Complexity Score (0-100)

Factors:
- **Blinding complexity**
- **Dose modifications**
- **Safety monitoring intensity**
- **Regulatory requirements**
- **Multi-country coordination**

```python
def calculate_operational_complexity(protocol):
    score = 0
    
    # Blinding
    if protocol.intervention.blinding == "double-blind":
        score += 15
    elif protocol.intervention.blinding == "single-blind":
        score += 8
    
    # Safety monitoring
    if protocol.safety_monitoring.dsmb_required:
        score += 15
    if protocol.safety_monitoring.stopping_rules:
        score += 10
    score += protocol.safety_monitoring.interim_analyses * 5
    
    # Intervention complexity
    if protocol.intervention.dose_modifications:
        score += 10
    
    # Geography
    score += min(20, len(protocol.basic_info.geography) * 5)
    
    return min(100, score)
```

### 4. Amendment Risk Score (0-100)

Predictive score based on protocol characteristics that historically lead to amendments.

### 5. Monitoring Complexity Score (0-100)

Based on endpoint complexity, safety requirements, and data collection burden.

## Output: Protocol Analysis Report

```json
{
  "protocol_id": "PROTO-2024-001",
  "analysis_date": "2024-01-15",
  
  "scores": {
    "enrollment_difficulty": {
      "score": 45,
      "level": "moderate",
      "factors": [
        "Biomarker requirement (HbA1c range)",
        "Stable medication requirement",
        "Moderate exclusion criteria count"
      ]
    },
    "site_burden": {
      "score": 55,
      "level": "moderate-high",
      "factors": [
        "12 visits over 24 weeks",
        "CGM device training required",
        "Central lab coordination"
      ]
    },
    "operational_complexity": {
      "score": 50,
      "level": "moderate",
      "factors": [
        "Double-blind design",
        "DSMB required",
        "Multi-country (3 regions)"
      ]
    },
    "amendment_risk": {
      "score": 35,
      "level": "low-moderate"
    },
    "overall_complexity": {
      "score": 46,
      "level": "moderate"
    }
  },
  
  "enrollment_analysis": {
    "predicted_screen_failure_rate": "35%",
    "bottlenecks": [
      {
        "criterion": "HbA1c 7.0-10.0%",
        "impact": "high",
        "recommendation": "Consider widening to 6.5-10.5%"
      },
      {
        "criterion": "Stable metformin ≥3 months",
        "impact": "medium",
        "recommendation": "May limit pool; consider 2 months"
      }
    ],
    "competing_trials": 12,
    "estimated_enrollment_rate": "1.5 patients/site/month"
  },
  
  "site_requirements": {
    "must_have": [
      "Endocrinology/diabetes expertise",
      "CGM device experience",
      "Central lab connectivity"
    ],
    "preferred": [
      "Prior Phase II experience in T2DM",
      "High enrollment capacity",
      "Diverse patient population"
    ],
    "equipment": [
      "CGM devices and training capability"
    ]
  },
  
  "recommended_site_profile": {
    "type": "Academic medical center or large community practice",
    "experience": "≥3 T2DM trials in past 5 years",
    "capacity": "≥50 T2DM patients in practice",
    "geography_priority": ["US Midwest", "US Southeast", "Germany"]
  },
  
  "recommended_pi_profile": {
    "specialty": "Endocrinology",
    "experience": "Phase II+ diabetes trials",
    "publication_focus": "T2DM, metabolic disease",
    "minimum_trials": 5
  },
  
  "optimization_suggestions": [
    {
      "area": "Enrollment",
      "suggestion": "Consider remote screening visits to expand reach",
      "impact": "Could improve enrollment by 15-20%"
    },
    {
      "area": "Site Burden",
      "suggestion": "Combine Week 4 and Week 6 visits if clinically appropriate",
      "impact": "Reduces site burden score by ~5 points"
    }
  ]
}
```

## Integration with Existing System

### Enhanced Recommendation Query

Current flow:
```
User: "Find PIs for diabetes trial"
→ Vector search on trial descriptions
→ Return PI/site matches
```

New flow with Protocol Intelligence:
```
User: Uploads protocol OR enters structured data
→ Parse to structured JSON
→ Calculate operational scores
→ Generate site/PI requirements
→ Filter recommendations by:
   - Required capabilities (imaging, devices, etc.)
   - Experience in indication
   - Historical enrollment performance
   - Geographic match
→ Return ranked PI/site matches with fit scores
```

### New API Endpoints

```
POST /api/protocol/analyze
  - Input: Protocol PDF or structured JSON
  - Output: Full analysis report with scores

POST /api/protocol/recommend
  - Input: Protocol analysis + preferences
  - Output: Ranked PI/site recommendations

GET /api/protocol/{id}/scores
  - Output: Operational scores for saved protocol
```

## Demo Implementation Plan

### Phase 1: Structured Input (For Demo)
- Build input form for protocol details
- Implement scoring engine
- Display analysis dashboard

### Phase 2: PDF Parsing (Post-Demo)
- Integrate PDF extraction (PyPDF2, pdfplumber)
- LLM-based section parsing
- Structured data extraction

### Phase 3: Full Integration
- Connect to PI/site recommendation engine
- Historical performance matching
- Competing trial analysis

## UI Mockup for Demo

```
┌─────────────────────────────────────────────────────────────────┐
│  PROTOCOL INTELLIGENCE                                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │ PROTOCOL INPUT      │  │ OPERATIONAL SCORES              │  │
│  │                     │  │                                 │  │
│  │ Indication: [____]  │  │  Enrollment     ████████░░ 45   │  │
│  │ Phase: [dropdown]   │  │  Site Burden    █████████░ 55   │  │
│  │ Enrollment: [___]   │  │  Complexity     ████████░░ 50   │  │
│  │                     │  │  Amendment Risk ██████░░░░ 35   │  │
│  │ [+ Add Criteria]    │  │                                 │  │
│  │ [+ Add Endpoints]   │  │  Overall: MODERATE (46)         │  │
│  │                     │  │                                 │  │
│  │ [Analyze Protocol]  │  └─────────────────────────────────┘  │
│  └─────────────────────┘                                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ENROLLMENT BOTTLENECKS                                    │  │
│  │                                                           │  │
│  │ ⚠️ HbA1c 7.0-10.0% - HIGH IMPACT                         │  │
│  │    Recommendation: Consider widening to 6.5-10.5%        │  │
│  │                                                           │  │
│  │ ⚠️ Stable metformin ≥3 months - MEDIUM IMPACT            │  │
│  │    Recommendation: Consider reducing to 2 months         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ RECOMMENDED PI/SITE PROFILE                               │  │
│  │                                                           │  │
│  │ Site Type: Academic medical center                        │  │
│  │ Experience: ≥3 T2DM trials in past 5 years               │  │
│  │ Must Have: CGM experience, Central lab connectivity       │  │
│  │                                                           │  │
│  │ [Find Matching PIs →]                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```
