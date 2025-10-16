"""
Sistema de Transcrição de Vídeos do YouTube
Busca legendas/transcrições automáticas e formata o texto de forma legível.
Versão robusta com múltiplas tentativas e tratamento de erros.
"""

import logging
from typing import Optional, Dict, List
import re
import asyncio

logger = logging.getLogger(__name__)

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled, 
        NoTranscriptFound,
        VideoUnavailable,
        TooManyRequests,
        YouTubeRequestFailed
    )
    TRANSCRIPT_API_AVAILABLE = True
except ImportError as e:
    logger.error(f"Erro ao importar youtube_transcript_api: {e}")
    TRANSCRIPT_API_AVAILABLE = False


class VideoTranscriber:
    """
    Classe responsável por buscar e formatar transcrições de vídeos do YouTube.
    """
    
    def __init__(self):
        """Inicializa o transcritor"""
        if not TRANSCRIPT_API_AVAILABLE:
            logger.error("youtube_transcript_api não está disponível!")
        else:
            logger.info("VideoTranscriber inicializado com sucesso")
    
    
    def extract_video_id(self, url_or_id: str) -> Optional[str]:
        """
        Extrai o ID do vídeo de uma URL do YouTube ou retorna o ID se já for um ID.
        """
        if len(url_or_id) == 11 and not '/' in url_or_id:
            return url_or_id
        
        match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11}).*', url_or_id)
        if match:
            return match.group(1)
        
        match = re.search(r'youtu\.be/([0-9A-Za-z_-]{11})', url_or_id)
        if match:
            return match.group(1)
        
        return None
    
    
    def clean_text(self, text: str) -> str:
        """
        Limpa o texto removendo caracteres estranhos e normalizando espaços.
        """
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        text = re.sub(r'([.,!?;:])([^\s])', r'\1 \2', text)
        text = text.strip()
        return text
    
    
    def split_into_paragraphs(self, text: str, sentences_per_paragraph: int = 4) -> str:
        """
        Divide o texto em parágrafos para ficar mais legível.
        """
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        paragraphs = []
        current_paragraph = []
        
        for sentence in sentences:
            current_paragraph.append(sentence)
            
            if len(current_paragraph) >= sentences_per_paragraph:
                paragraphs.append(' '.join(current_paragraph))
                current_paragraph = []
        
        if current_paragraph:
            paragraphs.append(' '.join(current_paragraph))
        
        return '\n\n'.join(paragraphs)
    
    
    async def get_transcript(self, video_id: str) -> Dict:
        """
        Busca a transcrição de um vídeo do YouTube NO IDIOMA ORIGINAL.
        Versão robusta com múltiplas tentativas.
        """
        if not TRANSCRIPT_API_AVAILABLE:
            return {
                'success': False,
                'error': 'Biblioteca de transcrição não disponível',
                'video_id': video_id
            }
        
        try:
            logger.info(f"🎬 Buscando transcrição do vídeo: {video_id}")
            
            transcript_list = None
            transcript = None
            detected_language = None
            language_name = None
            
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                logger.info(f"   ✅ Lista de transcrições obtida com sucesso")
            except TranscriptsDisabled:
                logger.error(f"   ❌ Transcrições desabilitadas")
                return {
                    'success': False,
                    'error': 'O criador do vídeo desabilitou as transcrições',
                    'video_id': video_id
                }
            except NoTranscriptFound:
                logger.error(f"   ❌ Nenhuma transcrição encontrada")
                return {
                    'success': False,
                    'error': 'Nenhuma transcrição disponível para este vídeo',
                    'video_id': video_id
                }
            except VideoUnavailable:
                logger.error(f"   ❌ Vídeo indisponível")
                return {
                    'success': False,
                    'error': 'Vídeo não encontrado ou indisponível',
                    'video_id': video_id
                }
            except Exception as e:
                logger.error(f"   ❌ Erro ao listar transcrições: {e}")
                return {
                    'success': False,
                    'error': f'Erro ao acessar transcrições: {str(e)}',
                    'video_id': video_id
                }
            
            try:
                logger.info(f"   Buscando transcrição gerada automaticamente...")
                for t in transcript_list:
                    if t.is_generated:
                        transcript = t
                        detected_language = t.language_code
                        language_name = t.language
                        logger.info(f"   ✅ Encontrada transcrição automática: {language_name} ({detected_language})")
                        break
            except Exception as e:
                logger.warning(f"   ⚠️ Erro ao buscar automática: {e}")
            
            if not transcript:
                try:
                    logger.info(f"   Buscando qualquer transcrição disponível...")
                    for t in transcript_list:
                        transcript = t
                        detected_language = t.language_code
                        language_name = t.language
                        logger.info(f"   ✅ Encontrada: {language_name} ({detected_language})")
                        break
                except Exception as e:
                    logger.warning(f"   ⚠️ Erro ao buscar qualquer: {e}")
            
            if not transcript:
                logger.error(f"   ❌ Nenhuma transcrição disponível")
                return {
                    'success': False,
                    'error': 'Nenhuma transcrição disponível para este vídeo',
                    'video_id': video_id
                }
            
            try:
                logger.info(f"   Buscando dados da transcrição...")
                transcript_data = transcript.fetch()
                logger.info(f"   ✅ Dados obtidos: {len(transcript_data)} segmentos")
            except Exception as e:
                logger.error(f"   ❌ Erro ao buscar dados: {e}")
                return {
                    'success': False,
                    'error': f'Erro ao baixar transcrição: {str(e)}',
                    'video_id': video_id
                }
            
            if not transcript_data:
                logger.error(f"   ❌ Transcrição vazia")
                return {
                    'success': False,
                    'error': 'Transcrição está vazia',
                    'video_id': video_id
                }
            
            raw_text = ' '.join([item['text'] for item in transcript_data])
            
            cleaned_text = self.clean_text(raw_text)
            
            formatted_text = self.split_into_paragraphs(cleaned_text)
            
            logger.info(f"✅ Transcrição obtida com sucesso!")
            logger.info(f"   Idioma: {language_name} ({detected_language})")
            logger.info(f"   Caracteres: {len(formatted_text)}")
            
            return {
                'success': True,
                'text': formatted_text,
                'raw_text': cleaned_text,
                'language': detected_language,
                'language_name': language_name,
                'video_id': video_id,
                'length': len(formatted_text)
            }
        
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao buscar transcrição: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': f'Erro ao buscar transcrição: {str(e)}',
                'video_id': video_id
            }
    
    
    async def get_transcript_from_url(self, url: str) -> Dict:
        """
        Busca transcrição a partir de uma URL completa do YouTube.
        """
        video_id = self.extract_video_id(url)
        
        if not video_id:
            return {
                'success': False,
                'error': 'Não foi possível extrair o ID do vídeo da URL',
                'url': url
            }
        
        return await self.get_transcript(video_id)
