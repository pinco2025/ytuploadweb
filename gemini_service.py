"""
Gemini AI Service for generating SEO-optimized content
"""

import google.generativeai as genai
import os
import logging
from typing import Dict, Optional, Tuple
import re

logger = logging.getLogger(__name__)

class GeminiService:
    """Service for generating SEO-optimized content using Google's Gemini AI"""
    
    def __init__(self):
        """Initialize the Gemini service with API key"""
        self.api_key = os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        # Configure the API
        genai.configure(api_key=self.api_key)
        
        # Initialize the model
        try:
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            logger.info("Gemini service initialized successfully with gemini-1.5-flash model")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini model: {e}")
            raise
    
    def generate_content(self, filename: str, platform: str = "youtube") -> Dict[str, str]:
        """
        Generate SEO-optimized content based on filename and platform
        
        Args:
            filename: Video filename to extract topic from
            platform: "youtube" or "instagram"
            
        Returns:
            Dictionary with 'title', 'description', 'hashtags', and 'success' status
        """
        try:
            # Extract topic from filename
            topic = self._extract_topic(filename)
            if not topic:
                return self._create_error_response("Could not extract topic from filename")
            
            logger.info(f"Generating content for topic: '{topic}' on platform: {platform}")
            
            # Generate content based on platform
            if platform.lower() == "youtube":
                return self._generate_youtube_content(topic)
            elif platform.lower() == "instagram":
                return self._generate_instagram_content(topic)
            else:
                return self._create_error_response(f"Unsupported platform: {platform}")
                
        except Exception as e:
            logger.error(f"Error in generate_content: {e}")
            return self._create_error_response(f"Generation failed: {str(e)}")
    
    def _extract_topic(self, filename: str) -> str:
        """Extract meaningful topic from filename"""
        if not filename:
            return ""
        
        # Remove file extensions
        name = re.sub(r'\.(mp4|avi|mov|mkv|wmv|flv|webm|m4v)$', '', filename, flags=re.IGNORECASE)
        
        # Remove common prefixes/suffixes
        name = re.sub(r'^[0-9\s\-_\.]+', '', name)  # Leading numbers/spaces/dashes
        name = re.sub(r'[0-9\s\-_\.]+$', '', name)  # Trailing numbers/spaces/dashes
        
        # Clean up separators
        name = re.sub(r'[_-]+', ' ', name)  # Replace underscores/dashes with spaces
        name = re.sub(r'\s+', ' ', name)    # Normalize spaces
        name = name.strip()
        
        return name
    
    def _generate_youtube_content(self, topic: str) -> Dict[str, str]:
        """Generate YouTube-specific content"""
        prompt = f"""
Create SEO-optimized content for a YouTube Shorts video about "{topic}".

Format your response exactly like this:
TITLE: [compelling title under 100 characters]
DESCRIPTION: [engaging description with hook, key points, call to action]
HASHTAGS: [exactly 15 relevant hashtags separated by spaces]

Requirements:
- Title: Clickable, includes topic, uses power words
- Description: Hook in first line, key points, call to action, under 5000 chars
- Hashtags: Include #shorts #viral #trending plus topic-specific tags (exactly 15 total)
"""
        
        return self._call_gemini_api(prompt, "youtube")
    
    def _generate_instagram_content(self, topic: str) -> Dict[str, str]:
        """Generate Instagram-specific content"""
        prompt = f"""
Create SEO-optimized content for an Instagram Reel about "{topic}".

Format your response exactly like this:
TITLE: [engaging caption title under 125 characters with emojis]
DESCRIPTION: [engaging caption with hook, emojis, line breaks, under 2200 chars]
HASHTAGS: [exactly 20 relevant hashtags separated by spaces]

Requirements:
- Title: Engaging, uses emojis appropriately
- Description: Hook, key points, call to action, emojis, line breaks
- Hashtags: Include #reels #viral #trending plus topic-specific tags (exactly 20 total)
"""
        
        return self._call_gemini_api(prompt, "instagram")
    
    def _call_gemini_api(self, prompt: str, platform: str) -> Dict[str, str]:
        """Make API call to Gemini with error handling"""
        try:
            logger.info(f"Calling Gemini API for {platform}")
            
            # Generate content
            response = self.model.generate_content(prompt)
            
            if not response or not response.text:
                logger.error("Empty response from Gemini API")
                return self._create_error_response("Empty response from API")
            
            logger.info(f"Received response: {len(response.text)} characters")
            
            # Parse the response
            parsed = self._parse_response(response.text)
            
            if not parsed['success']:
                logger.error(f"Failed to parse response: {parsed['error']}")
                return parsed
            
            # Validate content
            if not self._validate_content(parsed, platform):
                logger.error("Generated content failed validation")
                return self._create_error_response("Generated content is invalid")
            
            logger.info(f"Successfully generated {platform} content")
            return {
                'success': True,
                'title': parsed['title'],
                'description': parsed['description'],
                'hashtags': parsed['hashtags'],
                'platform': platform
            }
            
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            return self._create_error_response(f"API call failed: {str(e)}")
    
    def _parse_response(self, response_text: str) -> Dict[str, str]:
        """Parse Gemini response into structured content"""
        try:
            lines = response_text.strip().split('\n')
            result = {'title': '', 'description': '', 'hashtags': '', 'success': False}
            
            current_section = None
            content_lines = []
            
            for line in lines:
                line = line.strip()
                
                if line.startswith('TITLE:'):
                    if current_section == 'title':
                        result['title'] = ' '.join(content_lines)
                    current_section = 'title'
                    content_lines = [line.replace('TITLE:', '').strip()]
                    
                elif line.startswith('DESCRIPTION:'):
                    if current_section == 'title':
                        result['title'] = ' '.join(content_lines)
                    elif current_section == 'description':
                        result['description'] = ' '.join(content_lines)
                    current_section = 'description'
                    content_lines = [line.replace('DESCRIPTION:', '').strip()]
                    
                elif line.startswith('HASHTAGS:'):
                    if current_section == 'title':
                        result['title'] = ' '.join(content_lines)
                    elif current_section == 'description':
                        result['description'] = ' '.join(content_lines)
                    current_section = 'hashtags'
                    content_lines = [line.replace('HASHTAGS:', '').strip()]
                    
                elif line and current_section:
                    content_lines.append(line)
            
            # Set the final section
            if current_section == 'hashtags':
                result['hashtags'] = ' '.join(content_lines)
            elif current_section == 'description':
                result['description'] = ' '.join(content_lines)
            elif current_section == 'title':
                result['title'] = ' '.join(content_lines)
            
            # Check if we got all required sections
            if result['title'] and result['description'] and result['hashtags']:
                result['success'] = True
                return result
            else:
                return self._create_error_response("Incomplete response from API")
                
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return self._create_error_response(f"Failed to parse response: {str(e)}")
    
    def _validate_content(self, content: Dict[str, str], platform: str) -> bool:
        """Validate generated content meets requirements"""
        try:
            title = content.get('title', '')
            description = content.get('description', '')
            hashtags = content.get('hashtags', '')
            
            # Check if content exists
            if not title or not description or not hashtags:
                return False
            
            # Validate hashtag count
            hashtag_list = hashtags.split()
            max_hashtags = 20  # Maximum allowed hashtags
            
            if len(hashtag_list) > max_hashtags:
                logger.warning(f"Too many hashtags generated: {len(hashtag_list)} (max {max_hashtags})")
                # Truncate hashtags to limit
                content['hashtags'] = ' '.join(hashtag_list[:max_hashtags])
                logger.info(f"Truncated hashtags to {max_hashtags}")
            
            # Platform-specific validation
            if platform == "youtube":
                if len(title) > 100:
                    logger.warning(f"YouTube title too long: {len(title)} chars")
                    return False
                if len(description) > 5000:
                    logger.warning(f"YouTube description too long: {len(description)} chars")
                    return False
                    
            elif platform == "instagram":
                if len(title) > 125:
                    logger.warning(f"Instagram title too long: {len(title)} chars")
                    return False
                if len(description) > 2200:
                    logger.warning(f"Instagram description too long: {len(description)} chars")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating content: {e}")
            return False
    
    def _create_error_response(self, error_message: str) -> Dict[str, str]:
        """Create standardized error response"""
        return {
            'success': False,
            'error': error_message,
            'title': '',
            'description': '',
            'hashtags': ''
        }
    
    def test_connection(self) -> Dict[str, any]:
        """Test the Gemini API connection"""
        try:
            test_prompt = "Say 'Hello, Gemini is working!'"
            response = self.model.generate_content(test_prompt)
            
            if response and response.text:
                return {
                    'success': True,
                    'message': 'Gemini API is working correctly',
                    'response': response.text
                }
            else:
                return {
                    'success': False,
                    'message': 'Empty response from Gemini API'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Gemini API test failed: {str(e)}',
                'error_type': type(e).__name__
            } 