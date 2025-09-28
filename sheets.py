import os
import json
import logging
from typing import List, Dict, Any
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

class SheetsManager:
    def __init__(self):
        # Get credentials from environment
        credentials_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
        sheets_url = os.environ.get("GOOGLE_SHEETS_URL")
        
        if not credentials_json or not sheets_url:
            raise ValueError("GOOGLE_SHEETS_CREDENTIALS and GOOGLE_SHEETS_URL environment variables are required")
        
        try:
            # Parse credentials JSON
            credentials_data = json.loads(credentials_json)
            
            # Fix private key format - ensure proper line breaks
            if 'private_key' in credentials_data:
                private_key = credentials_data['private_key']
                # Replace \\n with actual line breaks
                private_key = private_key.replace('\\n', '\n')
                credentials_data['private_key'] = private_key
            
            # Set up credentials
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = Credentials.from_service_account_info(
                credentials_data, 
                scopes=scopes
            )
            
            # Initialize gspread client
            self.gc = gspread.authorize(credentials)
            
            # Open the spreadsheet
            self.spreadsheet = self.gc.open_by_url(sheets_url)
            
            logger.info("Google Sheets client initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Google Sheets: {e}")
            raise

    async def get_canais(self) -> List[Dict[str, Any]]:
        """Get canais from Google Sheets"""
        try:
            # Get the first worksheet (canais_para_monitorar)
            worksheet = self.spreadsheet.worksheet("canais_para_monitorar")
            
            # Get all records (assumes header row)
            records = worksheet.get_all_records()
            
            canais = []
            for record in records:
                # Skip empty rows
                if not record.get('nome_canal') or not record.get('url_canal'):
                    continue
                
                canal_data = {
                    'nome_canal': record.get('nome_canal', '').strip(),
                    'url_canal': record.get('url_canal', '').strip(),
                    'nicho': record.get('nicho', '').strip(),
                    'subnicho': record.get('subnicho', '').strip(),
                    'status': record.get('status', 'ativo').strip().lower()
                }
                
                # Validate required fields
                if canal_data['nome_canal'] and canal_data['url_canal']:
                    canais.append(canal_data)
            
            logger.info(f"Retrieved {len(canais)} canais from Google Sheets")
            return canais
            
        except Exception as e:
            logger.error(f"Error getting canais from sheets: {e}")
            raise

    async def add_canal(self, canal_data: Dict[str, Any]) -> bool:
        """Add a new canal to Google Sheets"""
        try:
            worksheet = self.spreadsheet.worksheet("canais_para_monitorar")
            
            # Prepare row data
            row_data = [
                canal_data.get('nome_canal', ''),
                canal_data.get('url_canal', ''),
                canal_data.get('nicho', ''),
                canal_data.get('subnicho', ''),
                canal_data.get('status', 'ativo')
            ]
            
            # Append row
            worksheet.append_row(row_data)
            logger.info(f"Added canal to sheets: {canal_data.get('nome_canal')}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding canal to sheets: {e}")
            return False

    async def update_canal_status(self, nome_canal: str, status: str) -> bool:
        """Update canal status in Google Sheets"""
        try:
            worksheet = self.spreadsheet.worksheet("canais_para_monitorar")
            
            # Find the canal row
            records = worksheet.get_all_records()
            for i, record in enumerate(records, start=2):  # Start at row 2 (after header)
                if record.get('nome_canal') == nome_canal:
                    # Update status column (assuming it's column E)
                    worksheet.update_cell(i, 5, status)
                    logger.info(f"Updated status for {nome_canal}: {status}")
                    return True
            
            logger.warning(f"Canal not found in sheets: {nome_canal}")
            return False
            
        except Exception as e:
            logger.error(f"Error updating canal status: {e}")
            return False

    def validate_sheet_structure(self) -> bool:
        """Validate that the sheet has the correct structure"""
        try:
            worksheet = self.spreadsheet.worksheet("canais_para_monitorar")
            
            # Check if headers exist
            headers = worksheet.row_values(1)
            expected_headers = ['nome_canal', 'url_canal', 'nicho', 'subnicho', 'status']
            
            for header in expected_headers:
                if header not in headers:
                    logger.error(f"Missing header: {header}")
                    return False
            
            logger.info("Sheet structure validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Error validating sheet structure: {e}")
            return False

    async def create_backup_sheet(self) -> bool:
        """Create a backup sheet with current data"""
        try:
            from datetime import datetime
            
            # Create backup worksheet name
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Get current data
            source_worksheet = self.spreadsheet.worksheet("canais_para_monitorar")
            all_values = source_worksheet.get_all_values()
            
            # Create new worksheet
            backup_worksheet = self.spreadsheet.add_worksheet(
                title=backup_name,
                rows=len(all_values) + 10,  # Add some extra rows
                cols=5
            )
            
            # Copy data
            if all_values:
                backup_worksheet.update('A1', all_values)
            
            logger.info(f"Created backup sheet: {backup_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating backup sheet: {e}")
            return False

    async def get_sheet_stats(self) -> Dict[str, Any]:
        """Get statistics about the sheet"""
        try:
            worksheet = self.spreadsheet.worksheet("canais_para_monitorar")
            records = worksheet.get_all_records()
            
            total_canais = len([r for r in records if r.get('nome_canal')])
            active_canais = len([r for r in records if r.get('status', '').lower() == 'ativo'])
            
            # Count by nicho
            nichos = {}
            for record in records:
                nicho = record.get('nicho', 'Unknown')
                if nicho:
                    nichos[nicho] = nichos.get(nicho, 0) + 1
            
            return {
                'total_canais': total_canais,
                'active_canais': active_canais,
                'paused_canais': total_canais - active_canais,
                'nichos': nichos,
                'last_updated': worksheet.lastUpdateTime if hasattr(worksheet, 'lastUpdateTime') else None
            }
            
        except Exception as e:
            logger.error(f"Error getting sheet stats: {e}")
            return {}
