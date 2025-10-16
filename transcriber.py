"""
Sistema de Transcrição de Vídeos do YouTube - Versão com yt-dlp e VTT
"""

import logging
from typing import Optional, Dict
import re
import subprocess
import tempfile
import os

logger = logging.getLogger(__name__)


class VideoTranscriber:
    
    def __init__(self):
        logger.info("VideoTranscriber inicializado com yt-dlp (VTT)")
    
    
    def extract_video_id(self, url_or_id: str) -> Optional[str]:
        if len(url_or_id) == 11 and '/' not in url_or_id:
            return url_or_id
        
        match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})', url_or_id)
        if match:
            return match.group(1)
        
        return None
    
    
    def parse_vtt(self, vtt_content: str) -> str:
        lines = vtt_content.split('\n')
        texts = []
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
            if line.startswith('WEBVTT'):
                continue
            if line.startswith('Kind:'):
                continue
            if line.startswith('Language:'):
                continue
            if '-->' in line:
                continue
            if re.match(r'^\d+$', line):
                continue
            if line.startswith('<'):
                line = re.sub(r'<[^>]+>', '', line)
            
            if line:
                texts.append(line)
        
        return ' '.join(texts)
    
    
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
            logger.info(f"Buscando transcrição: {video_id}")
            
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            with tempfile.TemporaryDirectory() as temp_dir:
                subtitle_file = os.path.join(temp_dir, "subtitle")
                
                cmd = [
                    "yt-dlp",
                    "--skip-download",
                    "--write-auto-subs",
                    "--sub-format", "vtt",
                    "--sub-langs", "all",
                    "--no-warnings",
                    "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "-o", subtitle_file,
                    url
                ]
                
                logger.info("Executando yt-dlp...")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    logger.error(f"yt-dlp erro: {result.stderr}")
                    return {
                        'success': False,
                        'error': 'Legendas não disponíveis ou vídeo bloqueado',
                        'video_id': video_id
                    }
                
                vtt_files = [f for f in os.listdir(temp_dir) if f.endswith('.vtt')]
                
                if not vtt_files:
                    logger.warning("Nenhuma legenda VTT encontrada")
                    return {
                        'success': False,
                        'error': 'Nenhuma legenda disponível',
                        'video_id': video_id
                    }
                
                subtitle_path = os.path.join(temp_dir, vtt_files[0])
                
                language_code = "unknown"
                if "." in vtt_files[0]:
                    parts = vtt_files[0].split(".")
                    if len(parts) >= 2:
                        language_code = parts[-2]
                
                logger.info(f"Lendo arquivo VTT: {vtt_files[0]}")
                
                with open(subtitle_path, 'r', encoding='utf-8') as f:
                    vtt_content = f.read()
                
                raw_text = self.parse_vtt(vtt_content)
                
                if not raw_text or len(raw_text) < 10:
                    return {
                        'success': False,
                        'error': 'Legendas vazias ou inválidas',
                        'video_id': video_id
                    }
                
                cleaned = self.clean_text(raw_text)
                formatted = self.split_into_paragraphs(cleaned)
                
                logger.info(f"Sucesso! {len(formatted)} caracteres")
                
                return {
                    'success': True,
                    'text': formatted,
                    'raw_text': cleaned,
                    'language': language_code,
                    'language_name': language_code.upper(),
                    'video_id': video_id,
                    'length': len(formatted)
                }
                
        except subprocess.TimeoutExpired:
            logger.error("Timeout")
            return {
                'success': False,
                'error': 'Timeout ao buscar legendas',
                'video_id': video_id
            }
        except Exception as e:
            logger.error(f"Erro: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': f'Erro: {str(e)}',
                'video_id': video_id
            }
