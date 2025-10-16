"""
Sistema de Transcrição de Vídeos do YouTube - Versão com yt-dlp
"""

import logging
from typing import Optional, Dict
import re
import subprocess
import json
import tempfile
import os

logger = logging.getLogger(__name__)


class VideoTranscriber:
    
    def __init__(self):
        logger.info("VideoTranscriber inicializado com yt-dlp")
    
    
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
            logger.info(f"Buscando transcrição com yt-dlp: {video_id}")
            
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            with tempfile.TemporaryDirectory() as temp_dir:
                subtitle_file = os.path.join(temp_dir, "subtitle.%(ext)s")
                
                cmd = [
                    "yt-dlp",
                    "--skip-download",
                    "--write-auto-subs",
                    "--sub-format", "json3",
                    "--sub-langs", "all",
                    "-o", subtitle_file,
                    url
                ]
                
                logger.info(f"Executando: {' '.join(cmd)}")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    logger.error(f"yt-dlp falhou: {result.stderr}")
                    return {
                        'success': False,
                        'error': 'Não foi possível baixar legendas. Vídeo pode não ter legendas disponíveis.',
                        'video_id': video_id
                    }
                
                json_files = [f for f in os.listdir(temp_dir) if f.endswith('.json3')]
                
                if not json_files:
                    logger.warning(f"Nenhuma legenda encontrada para {video_id}")
                    return {
                        'success': False,
                        'error': 'Nenhuma legenda disponível para este vídeo',
                        'video_id': video_id
                    }
                
                subtitle_path = os.path.join(temp_dir, json_files[0])
                
                language_code = "unknown"
                if "." in json_files[0]:
                    parts = json_files[0].split(".")
                    if len(parts) >= 2:
                        language_code = parts[-2]
                
                with open(subtitle_path, 'r', encoding='utf-8') as f:
                    subtitle_data = json.load(f)
                
                texts = []
                if 'events' in subtitle_data:
                    for event in subtitle_data['events']:
                        if 'segs' in event:
                            for seg in event['segs']:
                                if 'utf8' in seg:
                                    texts.append(seg['utf8'])
                
                if not texts:
                    return {
                        'success': False,
                        'error': 'Legendas vazias ou formato inválido',
                        'video_id': video_id
                    }
                
                raw_text = ' '.join(texts)
                cleaned = self.clean_text(raw_text)
                formatted = self.split_into_paragraphs(cleaned)
                
                logger.info(f"Sucesso! {len(formatted)} caracteres em {language_code}")
                
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
            logger.error(f"Timeout ao buscar legendas de {video_id}")
            return {
                'success': False,
                'error': 'Timeout ao buscar legendas (vídeo muito longo ou conexão lenta)',
                'video_id': video_id
            }
        except Exception as e:
            logger.error(f"Erro: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': f'Erro ao buscar legendas: {str(e)}',
                'video_id': video_id
            }
