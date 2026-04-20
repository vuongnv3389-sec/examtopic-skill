#!/usr/bin/env python3
"""
Extract question, answers, and discussion content from ExamTopics HTML body files.
Outputs CSV with: exam_code, question_number, question_text, choices, correct_answer, 
answer_description, community_answers, discussion_summary
"""

import csv
import json
import re
from pathlib import Path
from html.parser import HTMLParser
from typing import Dict, List, Optional, Any
import argparse
from collections import defaultdict


class QuestionParser(HTMLParser):
    """Parse HTML to extract question, answers, and discussions."""
    
    def __init__(self):
        super().__init__()
        self.data = {
            'title': '',
            'exam_code': '',
            'question_number': '',
            'question_text': '',
            'choices': [],
            'correct_answer': '',
            'answer_description': '',
            'community_votes': {},
            'discussions': [],
            'images': [],
        }
        self.current_tag = None
        self.current_text = []
        self.in_question_body = False
        self.in_question_choices = False
        self.in_question_answer = False
        self.in_answer_description = False
        self.in_comment_content = False
        self.in_correct_answer = False
        self.in_voted_answers = False
        self.in_choice = False
        self.in_choice_letter = False
        self.choice_label = ''
        self.current_choice_text = []
        self.current_comment = []
        self.current_discussion = {
            'author': '',
            'content': '',
            'selected_answer': ''
        }
        self.voted_answers_json = None
        # Stack to track nested div contexts so closing inner divs don't
        # accidentally unset a containing section flag.
        self._section_stack: List[Optional[str]] = []
        
    def handle_starttag(self, tag: str, attrs: dict):
        """Handle opening tags."""
        attrs = dict(attrs)

        # Capture images when tags appear
        if tag == 'img':
            src = attrs.get('src') or attrs.get('data-src') or ''
            alt = attrs.get('alt', '')
            img_note = ''
            if src:
                img_note = f"[IMAGE: {src}]"
                # record image metadata
                self.data.setdefault('images', []).append({'src': src, 'alt': alt})

            # Insert placeholder text into the current collection context
            if img_note:
                if self.in_choice and not self.in_choice_letter:
                    self.current_choice_text.append(img_note)
                elif self.in_comment_content:
                    self.current_comment.append(img_note)
                elif self.in_question_body:
                    self.current_text.append(img_note)
        
        # Detect question body section
        if tag == 'div':
            classes = attrs.get('class', '').split()

            # Push a named marker for divs that open a known section so we
            # can pop it only when the matching closing div is seen.
            if 'question-body' in classes:
                self._section_stack.append('question_body')
                self.in_question_body = True
            elif 'question-choices-container' in classes:
                self._section_stack.append('question_choices')
                self.in_question_choices = True
            elif 'question-answer' in classes and 'bg-light' in classes:
                self._section_stack.append('question_answer')
                self.in_question_answer = True
            elif 'answer-description' in classes:
                # answer-description can be a div/span; treat as named section
                self._section_stack.append('answer_description')
                self.in_answer_description = True
            elif 'comment-content' in classes:
                self._section_stack.append('comment')
                self.in_comment_content = True
            elif 'comment-selected-answers' in classes:
                # this is usually an inner element; set selected answer placeholder
                self.current_discussion['selected_answer'] = ''
            else:
                # Generic div: push None to keep stack balanced for nested divs
                self._section_stack.append(None)
                
        elif tag == 'span':
            classes = attrs.get('class', '').split()
            if 'correct-answer' in classes:
                self.in_correct_answer = True
            elif 'answer-description' in classes:
                self.in_answer_description = True
            elif self.in_choice and 'multi-choice-letter' in classes:
                self.in_choice_letter = True
                choice_letter = attrs.get('data-choice-letter', '').strip().upper()
                if choice_letter:
                    self.choice_label = choice_letter

        elif tag == 'li' and self.in_question_choices:
            classes = attrs.get('class', '').split()
            if 'multi-choice-item' in classes:
                self.in_choice = True
                self.current_choice_text = []
                self.choice_label = ''
                
        elif tag == 'label' and self.in_question_choices:
            # Question choice label
            classes = attrs.get('class', '').split()
            if any('question-choice' in c for c in classes):
                self.in_choice = True
                
        elif tag == 'input' and self.in_question_choices:
            # Get choice letter from input tag
            choice_id = attrs.get('id', '')
            match = re.search(r'([A-F])', choice_id.upper())
            if match:
                self.choice_label = match.group(1)
                
        elif tag == 'script' and attrs.get('id', '').isdigit():
            # Voted answers JSON
            self.in_voted_answers = True
            self.voted_answers_json = ''
            
    def handle_endtag(self, tag: str):
        """Handle closing tags."""
        if tag == 'div':
            # Pop the most recent div context. Only unset flags when the
            # matching named section is popped — this prevents inner div
            # closures from stopping collection prematurely.
            if not self._section_stack:
                return
            popped = self._section_stack.pop()
            if popped == 'question_body':
                self.in_question_body = False
            elif popped == 'question_choices':
                self.in_question_choices = False
            elif popped == 'question_answer':
                self.in_question_answer = False
            elif popped == 'answer_description':
                self.in_answer_description = False
            elif popped == 'comment':
                self.in_comment_content = False
                # Save discussion when a comment block closes
                if self.current_comment:
                    content = ' '.join(self.current_comment).strip()
                    if content:
                        self.data['discussions'].append({
                            'content': content,
                            'selected_answer': self.current_discussion.get('selected_answer', '')
                        })
                self.current_comment = []
                
        elif tag == 'span':
            if self.in_correct_answer:
                self.in_correct_answer = False
            elif self.in_answer_description:
                self.in_answer_description = False
            elif self.in_choice_letter:
                self.in_choice_letter = False

        elif tag == 'li' and self.in_choice:
            self.in_choice = False
            choice_text = ' '.join(self.current_choice_text).strip()
            if choice_text:
                self.data['choices'].append({
                    'label': self.choice_label,
                    'text': choice_text
                })
            self.current_choice_text = []
            self.choice_label = ''
                
        elif tag == 'label' and self.in_choice:
            self.in_choice = False
            choice_text = ' '.join(self.current_choice_text).strip()
            if choice_text:
                self.data['choices'].append({
                    'label': self.choice_label,
                    'text': choice_text
                })
            self.current_choice_text = []
            self.choice_label = ''
            
        elif tag == 'script' and self.in_voted_answers:
            self.in_voted_answers = False
            # Parse JSON
            if self.voted_answers_json:
                try:
                    voted_data = json.loads(self.voted_answers_json)
                    if isinstance(voted_data, list):
                        for item in voted_data:
                            ans = item.get('voted_answers', '')
                            count = item.get('vote_count', 0)
                            self.data['community_votes'][ans] = count
                except json.JSONDecodeError:
                    pass
            self.voted_answers_json = None
            
    def handle_data(self, data: str):
        """Handle text content."""
        text = data.strip()
        
        if not text:
            return
            
        # Collect voted answers JSON
        if self.in_voted_answers:
            self.voted_answers_json = (self.voted_answers_json or '') + data
            
        # Collect question text only when in the question body and not inside
        # choices/answer/voted JSON sections. Using the section stack above
        # ensures nested divs won't prematurely unset `in_question_body`.
        if (
            self.in_question_body
            and not self.in_question_choices
            and not self.in_voted_answers
            and not self.in_question_answer
        ):
            self.current_text.append(text)
            
        # Collect correct answer
        if self.in_correct_answer:
            self.data['correct_answer'] = text
            
        # Collect answer description
        if self.in_answer_description:
            self.data['answer_description'] = (
                self.data.get('answer_description', '') + ' ' + text
            ).strip()
            
        # Collect choice text
        if self.in_choice and not self.in_choice_letter:
            self.current_choice_text.append(text)
            
        # Collect discussion content
        if self.in_comment_content:
            if not text.startswith('This is a voting comment'):
                self.current_comment.append(text)
                
        # Extract selected answer from badge
        if 'Selected Answer:' in text:
            # Extract the answer letter
            match = re.search(r'Selected Answer:\s*([A-F])', text)
            if match:
                self.current_discussion['selected_answer'] = match.group(1)


def extract_question_info(html_content: str) -> Dict[str, Any]:
    """Extract question information from HTML content."""
    parser = QuestionParser()
    try:
        parser.feed(html_content)
    except Exception as e:
        print(f"Warning: Error parsing HTML: {e}")
    
    # Extract exam code and question number from title
    title = parser.data.get('title', '')
    match = re.search(r'Exam\s+([A-Z0-9-]+)\s+topic\s+(\d+)\s+question\s+(\d+)', title, re.IGNORECASE)
    if match:
        parser.data['exam_code'] = match.group(1)
        parser.data['topic_number'] = match.group(2)
        parser.data['question_number'] = match.group(3)
        
    # Join question text
    parser.data['question_text'] = ' '.join(parser.data.get('current_text', [])).strip()
    
    return parser.data


def process_body_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Process a single body file and extract question information."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        # Extract title from HTML
        title_match = re.search(r'<title>([^<]+)</title>', content)
        title = title_match.group(1) if title_match else ''
        
        # Parse HTML
        parser = QuestionParser()
        parser.data['title'] = title
        
        try:
            parser.feed(content)
        except Exception as e:
            print(f"Warning: Error parsing {file_path.name}: {e}")
            
        # Extract exam code and question number from URL filename
        filename = file_path.stem
        url_match = re.search(r'question-(\d+)', content)
        question_num = url_match.group(1) if url_match else ''
        
        # Extract exam code from filename or content
        exam_match = re.search(r'exam-([a-z0-9-]+)-topic', content, re.IGNORECASE)
        exam_code = exam_match.group(1).upper() if exam_match else ''
        
        # Clean up question text
        question_text = ' '.join(parser.current_text).strip()
        
        return {
            'file': filename,
            'exam_code': exam_code,
            'question_number': question_num,
            'title': title,
            'question_text': question_text,
            'choices': parser.data.get('choices', []),
            'correct_answer': parser.data.get('correct_answer', ''),
            'answer_description': parser.data.get('answer_description', ''),
            'community_votes': parser.data.get('community_votes', {}),
            'images': parser.data.get('images', []),
            'discussions_count': len(parser.data.get('discussions', [])),
            'discussions': parser.data.get('discussions', [])[:5],  # First 5 discussions
        }
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Extract question, answers, and discussions from ExamTopics HTML bodies'
    )
    parser.add_argument(
        'input_dir',
        help='Directory containing body files'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output CSV file (default: questions_answers.csv)',
        default='questions_answers.csv'
    )
    parser.add_argument(
        '-j', '--json',
        help='Also output detailed JSON file',
        action='store_true'
    )
    parser.add_argument(
        '-l', '--limit',
        type=int,
        help='Limit number of files to process',
        default=None
    )
    
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"Error: Directory not found: {input_dir}")
        return
        
    # Find all body/html/txt files
    patterns = ('*.body', '*.html', '*.txt')
    body_files = []
    for ptn in patterns:
        body_files.extend(sorted(input_dir.glob(ptn)))
    # keep order and remove duplicates
    seen = set()
    unique_files = []
    for f in body_files:
        if f.name in seen:
            continue
        seen.add(f.name)
        unique_files.append(f)
    body_files = unique_files
    if args.limit:
        body_files = body_files[:args.limit]
        
    if not body_files:
        print(f"No .body files found in {input_dir}")
        return
        
    print(f"Processing {len(body_files)} body files...")
    
    results = []
    for i, body_file in enumerate(body_files, 1):
        if body_file.name == 'index.jsonl':
            continue
            
        if i % 50 == 0:
            print(f"  Processed {i}/{len(body_files)}...")
            
        result = process_body_file(body_file)
        if result:
            results.append(result)
            
    print(f"Successfully processed {len(results)} files")
    
    # Write CSV output
    if results:
        csv_file = Path(args.output)
        csv_headers = [
            'exam_code', 'question_number', 'question_text',
            'choices_count', 'choices', 'correct_answer',
            'answer_description', 'community_votes', 'discussions_count', 'images'
        ]
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=csv_headers)
            writer.writeheader()
            
            for result in results:
                choices_str = ' | '.join([
                    f"{c['label']}: {c['text']}"
                    for c in result.get('choices', [])
                ])
                votes_str = ', '.join([
                    f"{k}:{v}" for k, v in result.get('community_votes', {}).items()
                ])
                images_list = result.get('images', []) or []
                images_str = ' | '.join([
                    (img.get('src') or '') + (f" ({img.get('alt')})" if img.get('alt') else '')
                    for img in images_list
                ])
                
                writer.writerow({
                    'exam_code': result.get('exam_code', ''),
                    'question_number': result.get('question_number', ''),
                    'question_text': result.get('question_text', ''),
                    'choices_count': len(result.get('choices', [])),
                    'choices': choices_str,
                    'correct_answer': result.get('correct_answer', ''),
                    'answer_description': result.get('answer_description', ''),
                    'community_votes': votes_str,
                    'discussions_count': result.get('discussions_count', 0),
                    'images': images_str,
                })
                
        print(f"CSV output saved to: {csv_file}")
        
    # Write JSON output if requested
    if args.json and results:
        json_file = Path(args.output).parent / (Path(args.output).stem + '_detailed.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"JSON output saved to: {json_file}")


if __name__ == '__main__':
    main()
