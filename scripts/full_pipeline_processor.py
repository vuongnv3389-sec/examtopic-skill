#!/usr/bin/env python3
"""
Full pipeline processor: Extract bodies from XML files, then extract questions.
Automatically discovers XML files, processes them, and aggregates results.
"""

import os
import sys
import json
import csv
import subprocess
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime


class FullPipelineProcessor:
    """End-to-end processing from XML to question extraction."""
    
    def __init__(self, base_dir: str, output_dir: str = None):
        self.base_dir = Path(base_dir)
        self.output_dir = Path(output_dir) if output_dir else self.base_dir / 'pipeline_results'
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results = defaultdict(dict)
        # Locate helper scripts (they live in scripts/ next to this file when bundled)
        script_dir = Path(__file__).resolve().parent
        self.extraction_script = script_dir / 'extract_burp_response_bodies.py'
        self.question_script = script_dir / 'extract_question_answers.py'
        
    def discover_xml_files(self):
        """Find all XML files to process."""
        xml_files = list(self.base_dir.rglob('*.xml'))
        # Filter out common non-exam XML files
        xml_files = [f for f in xml_files if not f.name.startswith('.')]
        return sorted(xml_files)
    
    def get_exam_code_from_filename(self, filepath: Path) -> str:
        """Extract exam code from file path."""
        # Try to extract from parent directories (e.g., CS0-003/CS0-003.xml)
        parent_name = filepath.parent.name
        if '-' in str(filepath.stem):
            return filepath.stem.split('_')[0]
        if parent_name and '-' in parent_name:
            return parent_name
        name = filepath.stem.replace('_', '-').upper()
        # Extract pattern like CS0-003
        import re
        match = re.search(r'([A-Z]+\d+-\d+)', name)
        if match:
            return match.group(1)
        return name
    
    def check_if_already_processed(self, xml_file: Path) -> bool:
        """Check if response_bodies already exist for this XML."""
        exam_code = self.get_exam_code_from_filename(xml_file)
        # Check possibility 1: same directory as XML file
        response_dir = xml_file.parent / f"{xml_file.stem}_response_bodies"
        if response_dir.exists():
            return True
        # Check possibility 2: exam code directory
        response_dir = xml_file.parent / f"{exam_code}_response_bodies"
        if response_dir.exists():
            return True
        # Check possibility 3: convention where HTML were fetched into
        # <exam_code>/question-response-bodies/
        response_dir = self.base_dir / exam_code / 'question-response-bodies'
        if response_dir.exists():
            return True
        return False
    
    def extract_bodies_from_xml(self, xml_file: Path) -> dict:
        """Extract response bodies from XML file."""
        exam_code = self.get_exam_code_from_filename(xml_file)
        
        # Check if already processed
        if self.check_if_already_processed(xml_file):
            print(f"   ⏭️  Already processed, skipping")
            return None
        
        print(f"   🔍 Extracting bodies from: {xml_file.name}")
        
        cmd = [
            'python3',
            str(self.extraction_script),
            str(xml_file)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.base_dir, timeout=300)
            
            if result.returncode != 0:
                print(f"   ❌ Error: {result.stderr[:200]}")
                return None
            
            # Parse output
            output_lines = result.stdout.strip().split('\n')
            for line in output_lines:
                print(f"   {line}")
                
            # Extract directory path from output
            for line in output_lines:
                if 'Output directory:' in line:
                    # Parse directory path
                    output_dir = line.split(':', 1)[1].strip()
                    return {
                        'status': 'success',
                        'xml_file': str(xml_file),
                        'output_dir': output_dir,
                        'exam_code': exam_code
                    }
            
            return None
            
        except subprocess.TimeoutExpired:
            print(f"   ❌ Extraction timeout")
            return None
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None
    
    def extract_questions_from_bodies(self, bodies_dir: Path, exam_code: str) -> dict:
        """Extract questions from response bodies."""
        print(f"   📊 Extracting questions...")
        
        output_file = self.output_dir / f"{exam_code}_questions.csv"
        json_file = self.output_dir / f"{exam_code}_questions_detailed.json"
        
        cmd = [
            'python3',
            str(self.question_script),
            str(bodies_dir),
            '-o', str(output_file),
            '-j'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                print(f"   ⚠️  Error: {result.stderr[:200]}")
                return None
            
            print(f"   ✅ Questions extracted to: {output_file.name}")
            
            # Count questions
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    count = sum(1 for _ in reader)
                return {
                    'status': 'success',
                    'csv_file': str(output_file),
                    'json_file': str(json_file),
                    'total_questions': count
                }
            except Exception as e:
                print(f"   ⚠️  Could not count results: {e}")
                return {
                    'status': 'partial',
                    'csv_file': str(output_file),
                    'json_file': str(json_file),
                    'error': str(e)
                }
            
        except subprocess.TimeoutExpired:
            print(f"   ❌ Question extraction timeout")
            return None
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None
    
    def process_xml_file(self, xml_file: Path):
        """Full pipeline: XML -> bodies -> questions."""
        print(f"\n{'='*60}")
        print(f"Processing: {xml_file.name}")
        print(f"{'='*60}")
        
        exam_code = self.get_exam_code_from_filename(xml_file)
        print(f"Exam Code: {exam_code}")
        
        # Step 1: Extract bodies
        bodies_result = self.extract_bodies_from_xml(xml_file)
        if not bodies_result:
            # Try to find existing response_bodies
            # Common locations: sibling *_response_bodies, or <exam_code>/question-response-bodies
            for candidate in xml_file.parent.rglob(f"*{exam_code}*_response_bodies"):
                if candidate.is_dir():
                    bodies_result = {'output_dir': str(candidate / 'bodies')}
                    print(f"   Found existing: {candidate.name}")
                    break
            if not bodies_result:
                candidate = self.base_dir / exam_code / 'question-response-bodies'
                if candidate.exists():
                    bodies_result = {'output_dir': str(candidate)}
                    print(f"   Found existing fetched HTML: {candidate}")
                    
        if not bodies_result:
            return None
        
        bodies_dir = Path(bodies_result['output_dir']) if isinstance(bodies_result['output_dir'], str) else Path(bodies_result.get('output_dir', ''))
        if not bodies_dir.exists():
            print(f"   ❌ Bodies directory not found: {bodies_dir}")
            return None
        
        # Step 2: Extract questions
        questions_result = self.extract_questions_from_bodies(bodies_dir, exam_code)
        
        if questions_result:
            self.results[exam_code] = {
                'xml_file': str(xml_file),
                'bodies_dir': str(bodies_dir),
                'questions_csv': questions_result.get('csv_file'),
                'questions_json': questions_result.get('json_file'),
                'total_questions': questions_result.get('total_questions', 0),
                'status': questions_result.get('status', 'success')
            }
            return self.results[exam_code]
        
        return None
    
    def create_comprehensive_summary(self):
        """Create comprehensive summary report."""
        summary_file = self.output_dir / 'pipeline_summary.json'
        csv_summary = self.output_dir / 'comprehensive_statistics.csv'
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'base_directory': str(self.base_dir),
            'output_directory': str(self.output_dir),
            'processed_exams': {}
        }
        
        total_exams = 0
        total_questions = 0
        
        for exam_code, data in self.results.items():
            summary['processed_exams'][exam_code] = data
            total_exams += 1
            total_questions += data.get('total_questions', 0)
        
        summary['totals'] = {
            'total_exams_processed': total_exams,
            'total_questions_extracted': total_questions
        }
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        # Create CSV
        with open(csv_summary, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'exam_code', 'total_questions', 'status', 'xml_file', 'csv_file'
            ])
            writer.writeheader()
            
            for exam_code in sorted(self.results.keys()):
                data = self.results[exam_code]
                writer.writerow({
                    'exam_code': exam_code,
                    'total_questions': data.get('total_questions', 0),
                    'status': data.get('status', 'unknown'),
                    'xml_file': Path(data.get('xml_file', '')).name,
                    'csv_file': Path(data.get('questions_csv', '')).name,
                })
        
        print(f"\n{'='*60}")
        print(f"PIPELINE SUMMARY")
        print(f"{'='*60}")
        print(f"Total exams processed: {total_exams}")
        print(f"Total questions extracted: {total_questions}")
        print(f"{'='*60}")
        
        if self.results:
            print(f"\nProcessed Exams:")
            for exam_code in sorted(self.results.keys()):
                data = self.results[exam_code]
                questions = data.get('total_questions', 0)
                status = data.get('status', 'unknown')
                print(f"  {exam_code:15} : {questions:6} questions ({status})")
        
        print(f"\n📋 Summary saved to: {summary_file}")
        print(f"📊 Statistics saved to: {csv_summary}")


def main():
    parser = argparse.ArgumentParser(
        description='Full pipeline: Extract bodies from XML, then extract questions'
    )
    parser.add_argument(
        'base_dir',
        help='Base directory containing XML files'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output directory (default: pipeline_results)',
        default=None
    )
    parser.add_argument(
        '--exam',
        help='Process specific exam code only',
        default=None
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of XML files to process',
        default=None
    )
    
    args = parser.parse_args()
    
    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        print(f"❌ Error: Directory not found: {base_dir}")
        sys.exit(1)
    
    processor = FullPipelineProcessor(str(base_dir), args.output)
    
    # Discover XML files
    print(f"🔍 Discovering XML files in: {base_dir}")
    xml_files = processor.discover_xml_files()
    
    if not xml_files:
        print("❌ No XML files found")
        sys.exit(1)
    
    print(f"✅ Found {len(xml_files)} XML files:")
    for xml_file in xml_files[:10]:
        print(f"   - {xml_file.name}")
    if len(xml_files) > 10:
        print(f"   ... and {len(xml_files)-10} more")
    
    # Filter by exam if specified
    if args.exam:
        xml_files = [f for f in xml_files if args.exam.lower() in f.name.lower()]
        print(f"\n🔍 Filtered to {len(xml_files)} files for exam: {args.exam}")
    
    # Limit if specified
    if args.limit:
        xml_files = xml_files[:args.limit]
    
    # Process each XML file
    for i, xml_file in enumerate(xml_files, 1):
        print(f"\n[{i}/{len(xml_files)}]")
        processor.process_xml_file(xml_file)
    
    # Create summary
    processor.create_comprehensive_summary()


if __name__ == '__main__':
    main()
