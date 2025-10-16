"""
Sistema de Transcrição de Vídeos do YouTube
Busca legendas/transcrições automáticas e formata o texto de forma legível.
"""

import logging
from typing import Optional, Dict, List
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled, 
    NoTranscriptFound,
    VideoUnavailable
)
import re

logger = logging.getLogger(__name__)


class VideoTranscriber:
    """
    Classe responsável por buscar e formatar transcrições de vídeos do YouTube.
    
    COMO FUNCIONA (explicação simples):
    1. Recebe o ID do vídeo (ex: "dQw4w9WgXcQ")
    2. Busca as legendas NO IDIOMA ORIGINAL do vídeo
    3. Limpa e organiza o texto
    4. Separa em parágrafos
    5. Retorna texto formatado e pronto para ler
    """
    
    def __init__(self):
        """Inicializa o transcritor"""
        logger.info("VideoTranscriber inicializado")
    
    
    def extract_video_id(self, url_or_id: str) -> Optional[str]:
        """
        Extrai o ID do vídeo de uma URL do YouTube ou retorna o ID se já for um ID.
        
        Exemplos que funciona:
        - "dQw4w9WgXcQ" → "dQw4w9WgXcQ"
        - "https://www.youtube.com/watch?v=dQw4w9WgXcQ" → "dQw4w9WgXcQ"
        - "https://youtu.be/dQw4w9WgXcQ" → "dQw4w9WgXcQ"
        
        Args:
            url_or_id: URL completa ou ID do vídeo
        
        Returns:
            ID do vídeo ou None se não conseguir extrair
        """
        # Se já for um ID válido (11 caracteres), retorna direto
        if len(url_or_id) == 11 and not '/' in url_or_id:
            return url_or_id
        
        # Tenta extrair de URL padrão: youtube.com/watch?v=XXXXX
        match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11}).*', url_or_id)
        if match:
            return match.group(1)
        
        # Tenta extrair de URL curta: youtu.be/XXXXX
        match = re.search(r'youtu\.be/([0-9A-Za-z_-]{11})', url_or_id)
        if match:
            return match.group(1)
        
        return None
    
    
    def clean_text(self, text: str) -> str:
        """
        Limpa o texto removendo caracteres estranhos e normalizando espaços.
        
        O que faz:
        - Remove quebras de linha duplas/triplas
        - Normaliza espaços múltiplos
        - Remove espaços antes de pontuação
        - Garante espaço depois de pontuação
        
        Args:
            text: Texto bruto
        
        Returns:
            Texto limpo
        """
        # Remove quebras de linha extras
        text = re.sub(r'\n+', ' ', text)
        
        # Remove espaços múltiplos
        text = re.sub(r'\s+', ' ', text)
        
        # Remove espaços antes de pontuação
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        
        # Garante espaço depois de pontuação (se não tiver)
        text = re.sub(r'([.,!?;:])([^\s])', r'\1 \2', text)
        
        # Remove espaços no início e fim
        text = text.strip()
        
        return text
    
    
    def split_into_paragraphs(self, text: str, sentences_per_paragraph: int = 4) -> str:
        """
        Divide o texto em parágrafos para ficar mais legível.
        
        ANALOGIA: É como quando você escreve uma redação e separa em parágrafos
        para não ficar um textão corrido impossível de ler.
        
        Args:
            text: Texto limpo
            sentences_per_paragraph: Quantas frases por parágrafo (padrão: 4)
        
        Returns:
            Texto formatado em parágrafos
        """
        # Divide em frases (por ponto final, interrogação, exclamação)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Agrupa frases em parágrafos
        paragraphs = []
        current_paragraph = []
        
        for sentence in sentences:
            current_paragraph.append(sentence)
            
            # Quando atingir o número de frases, cria um parágrafo
            if len(current_paragraph) >= sentences_per_paragraph:
                paragraphs.append(' '.join(current_paragraph))
                current_paragraph = []
        
        # Adiciona o último parágrafo (se tiver frases restantes)
        if current_paragraph:
            paragraphs.append(' '.join(current_paragraph))
        
        # Junta parágrafos com duas quebras de linha
        return '\n\n'.join(paragraphs)
    
    
    async def get_transcript(self, video_id: str) -> Optional[Dict]:
        """
        Busca a transcrição de um vídeo do YouTube NO IDIOMA ORIGINAL.
        
        COMO FUNCIONA:
        1. Busca TODAS as transcrições disponíveis
        2. Prioriza transcrições geradas automaticamente (idioma original)
        3. Se não tiver, pega a primeira disponível
        4. Formata o texto de forma legível
        
        Args:
            video_id: ID do vídeo (11 caracteres)
        
        Returns:
            Dicionário com:
            - success: True/False
            - text: Texto formatado (se sucesso)
            - raw_text: Texto sem formatação (se sucesso)
            - language: Idioma da transcrição
            - language_name: Nome do idioma em português
            - error: Mensagem de erro (se falha)
        """
        try:
            logger.info(f"🎬 Buscando transcrição do vídeo: {video_id}")
            
            # Busca lista de todas as transcrições disponíveis
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            transcript = None
            detected_language = None
            language_name = None
            
            # PRIORIDADE 1: Transcrição gerada automaticamente (idioma original)
            try:
                logger.info(f"   Buscando transcrição automática (idioma original)...")
                transcript = transcript_list.find_generated_transcript([])
                detected_language = transcript.language_code
                language_name = transcript.language
                logger.info(f"   ✅ Encontrada transcrição automática em: {language_name} ({detected_language})")
            except:
                pass
            
            # PRIORIDADE 2: Qualquer transcrição manual disponível
            if not transcript:
                try:
                    logger.info(f"   Sem transcrição automática. Buscando transcrição manual...")
                    transcript = transcript_list.find_manually_created_transcript([])
                    detected_language = transcript.language_code
                    language_name = transcript.language
                    logger.info(f"   ✅ Encontrada transcrição manual em: {language_name} ({detected_language})")
                except:
                    pass
            
            # PRIORIDADE 3: Primeira transcrição disponível (última tentativa)
            if not transcript:
                try:
                    logger.info(f"   Buscando qualquer transcrição disponível...")
                    for t in transcript_list:
                        transcript = t
                        detected_language = t.language_code
                        language_name = t.language
                        logger.info(f"   ✅ Encontrada em: {language_name} ({detected_language})")
                        break
                except:
                    pass
            
            # Se não encontrou NENHUMA transcrição
            if not transcript:
                logger.warning(f"   ❌ Nenhuma transcrição disponível para o vídeo {video_id}")
                return {
                    'success': False,
                    'error': 'Transcrição não disponível para este vídeo',
                    'video_id': video_id
                }
            
            # Busca o texto da transcrição
            transcript_data = transcript.fetch()
            
            # Extrai apenas o texto (sem timestamps)
            raw_text = ' '.join([item['text'] for item in transcript_data])
            
            # Limpa o texto
            cleaned_text = self.clean_text(raw_text)
            
            # Separa em parágrafos
            formatted_text = self.split_into_paragraphs(cleaned_text)
            
            logger.info(f"✅ Transcrição obtida com sucesso!")
            logger.info(f"   Idioma: {language_name} ({detected_language})")
            logger.info(f"   Caracteres: {len(formatted_text)}")
            
            return {
                'success': True,
                'text': formatted_text,           # Texto formatado (com parágrafos)
                'raw_text': cleaned_text,         # Texto limpo (sem parágrafos)
                'language': detected_language,    # Código do idioma (ex: 'en', 'pt')
                'language_name': language_name,   # Nome do idioma (ex: 'English', 'Portuguese')
                'video_id': video_id,
                'length': len(formatted_text)
            }
        
        except TranscriptsDisabled:
            logger.error(f"❌ Transcrições desabilitadas para o vídeo {video_id}")
            return {
                'success': False,
                'error': 'O criador do vídeo desabilitou as transcrições',
                'video_id': video_id
            }
        
        except NoTranscriptFound:
            logger.error(f"❌ Nenhuma transcrição encontrada para o vídeo {video_id}")
            return {
                'success': False,
                'error': 'Nenhuma transcrição disponível para este vídeo',
                'video_id': video_id
            }
        
        except VideoUnavailable:
            logger.error(f"❌ Vídeo indisponível: {video_id}")
            return {
                'success': False,
                'error': 'Vídeo não encontrado ou indisponível',
                'video_id': video_id
            }
        
        except Exception as e:
            logger.error(f"❌ Erro ao buscar transcrição do vídeo {video_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': f'Erro ao buscar transcrição: {str(e)}',
                'video_id': video_id
            }
    
    
    async def get_transcript_from_url(self, url: str) -> Optional[Dict]:
        """
        Busca transcrição a partir de uma URL completa do YouTube.
        
        Args:
            url: URL completa do vídeo
        
        Returns:
            Mesmo formato de get_transcript()
        """
        video_id = self.extract_video_id(url)
        
        if not video_id:
            return {
                'success': False,
                'error': 'Não foi possível extrair o ID do vídeo da URL',
                'url': url
            }
        
        return await self.get_transcript(video_id)
