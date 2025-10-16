"""
Sistema de Transcrição de Vídeos do YouTube - Versão Simplificada
"""

import logging
from typing import Optional, Dict
import re

logger = logging.getLogger(__name__)


class VideoTranscriber:
    
    def __init__(self):
        logger.info("VideoTranscriber inicializado")
    
    
    def extract_video_id(self, url_or_id: str) -> Optional[str]:
        if len(url_or_id) == 11 and '/' not in url_or_id:
            return url_or_id
        
        match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})', url_or_id)
        if match:
            return match.group(1)
        
        return None
    
    
    def clean_text(self, text: str) -> str:
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        return text
    
    
    def split_into_paragraphs(self, text: str) -> str:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        paragraphs = []
        current = []
        
        for sentence in sentences:
            current.append(sentence)
            if len(current) >= 4:
                paragraphs.append(' '.join(current))
                current = []
        
        if current:
            paragraphs.append(' '.join(current))
        
        return '\n\n'.join(paragraphs)
    
    
    async def get_transcript(self, video_id: str) -> Dict:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            
            logger.info(f"Buscando transcrição: {video_id}")
            
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            transcript = None
            language_name = "Unknown"
            language_code = "unknown"
            
            for t in transcript_list:
                transcript = t
                language_code = t.language_code
                language_name = t.language
                logger.info(f"Encontrada: {language_name}")
                break
            
            if not transcript:
                return {
                    'success': False,
                    'error': 'Nenhuma transcrição disponível',
                    'video_id': video_id
                }
            
            data = transcript.fetch()
            
            if not data:
                return {
                    'success': False,
                    'error': 'Transcrição vazia',
                    'video_id': video_id
                }
            
            raw_text = ' '.join([item['text'] for item in data])
            cleaned = self.clean_text(raw_text)
            formatted = self.split_into_paragraphs(cleaned)
            
            logger.info(f"Sucesso! {len(formatted)} caracteres")
            
            return {
                'success': True,
                'text': formatted,
                'raw_text': cleaned,
                'language': language_code,
                'language_name': language_name,
                'video_id': video_id,
                'length': len(formatted)
            }
            
        except ImportError:
            return {
                'success': False,
                'error': 'Biblioteca não instalada',
                'video_id': video_id
            }
        except Exception as e:
            logger.error(f"Erro: {e}")
            return {
                'success': False,
                'error': str(e),
                'video_id': video_id
            }
