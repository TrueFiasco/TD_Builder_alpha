"""
Error Monitor Service for Network Editor MCP
Provides error reporting by reading TouchDesigner's Error DAT.

Part of Phase 1 POC for TD Builder visual feedback integration.
Author: FELIX (Feature Engineer)
Date: 2024-12-25
"""

from typing import Any, List, Optional

import td
from utils.logging import log_message
from utils.types import LogLevel, Result


# Error DAT column mapping (standard TD Error DAT structure)
ERROR_DAT_COLUMNS = {
    'source': 0,      # Operator path that generated the error
    'message': 1,     # Error message text
    'absframe': 2,    # Absolute frame number when error occurred
    'frame': 3,       # Local frame number
    'severity': 4,    # Severity level (0=info, 1=warning, 2=error, 3=fatal)
    'type': 5,        # Operator type/family
}

# Severity level mapping
SEVERITY_MAP = {
    0: 'info',
    1: 'warning',
    2: 'error',
    3: 'fatal',
    '0': 'info',
    '1': 'warning',
    '2': 'error',
    '3': 'fatal',
}


class ErrorMonitorService:
    """
    Service for monitoring and reporting TouchDesigner errors.

    Provides:
    - Cook error aggregation from Error DAT
    - Error filtering by source operator
    - Structured error data for AI agent consumption
    """

    def __init__(self, error_dat_path: str = None):
        """
        Initialize the error monitor.

        Args:
            error_dat_path: Path to the Error DAT operator.
                            If None, will search for common locations.
        """
        self.error_dat_path = error_dat_path
        self._cached_error_dat = None
        log_message("ErrorMonitorService initialized", LogLevel.INFO)

    def _find_error_dat(self) -> Any:
        """
        Find the Error DAT operator.

        Searches common locations:
        1. Configured path
        2. /mcp_webserver_base/error_dat
        3. /project1/error_dat
        4. Global Error DAT reference
        """
        if self._cached_error_dat is not None:
            return self._cached_error_dat

        # Try configured path first
        if self.error_dat_path:
            error_dat = td.op(self.error_dat_path)
            if error_dat is not None:
                self._cached_error_dat = error_dat
                return error_dat

        # Try common locations
        common_paths = [
            '/mcp_webserver_base/error_dat',
            '/project1/error_dat',
            '/project1/error1',
            '/local/error_dat',
        ]

        for path in common_paths:
            error_dat = td.op(path)
            if error_dat is not None:
                self._cached_error_dat = error_dat
                log_message(f"Found Error DAT at: {path}", LogLevel.INFO)
                return error_dat

        return None

    def get_cook_errors(
        self,
        source_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        limit: int = 100
    ) -> Result:
        """
        Get all current cook errors from the Error DAT.

        Args:
            source_filter: Optional operator path to filter errors by
            severity_filter: Optional severity level to filter by ("info", "warning", "error", "fatal")
            limit: Maximum number of errors to return

        Returns:
            Result containing:
            - success: bool
            - data: {errors: [...], total_count: int} on success
            - error: error message on failure
        """
        try:
            error_dat = self._find_error_dat()

            if error_dat is None:
                log_message("No Error DAT found", LogLevel.WARNING)
                return {
                    'success': True,
                    'data': {
                        'errors': [],
                        'total_count': 0,
                        'note': 'No Error DAT configured or found'
                    }
                }

            errors = []
            num_rows = error_dat.numRows

            if num_rows <= 1:  # Only header row
                return {
                    'success': True,
                    'data': {
                        'errors': [],
                        'total_count': 0,
                        'note': 'Error DAT is empty'
                    }
                }

            # Parse errors from DAT (skip header row)
            for row_idx in range(1, min(num_rows, limit + 1)):
                try:
                    # Read cells by column name or index
                    source = self._get_cell(error_dat, row_idx, 'source')
                    message = self._get_cell(error_dat, row_idx, 'message')
                    absframe = self._get_cell(error_dat, row_idx, 'absframe', default=0)
                    frame = self._get_cell(error_dat, row_idx, 'frame', default=0)
                    severity_raw = self._get_cell(error_dat, row_idx, 'severity', default=0)
                    op_type = self._get_cell(error_dat, row_idx, 'type', default='')

                    # Convert severity to string
                    severity = SEVERITY_MAP.get(severity_raw, 'info')

                    # Apply source filter
                    if source_filter and source_filter not in source:
                        continue

                    # Apply severity filter
                    if severity_filter and severity != severity_filter:
                        continue

                    errors.append({
                        'source': source,
                        'message': message,
                        'absframe': int(absframe) if absframe else 0,
                        'frame': int(frame) if frame else 0,
                        'severity': severity,
                        'type': op_type,
                        'row_index': row_idx
                    })

                except Exception as row_error:
                    log_message(f"Error parsing row {row_idx}: {str(row_error)}", LogLevel.WARNING)
                    continue

            log_message(f"Retrieved {len(errors)} errors from Error DAT", LogLevel.INFO)

            return {
                'success': True,
                'data': {
                    'errors': errors,
                    'total_count': len(errors),
                    'error_dat_path': str(error_dat.path) if error_dat else None
                }
            }

        except Exception as e:
            log_message(f"Error reading Error DAT: {str(e)}", LogLevel.ERROR)
            return {
                'success': False,
                'error': f"Exception reading errors: {str(e)}"
            }

    def _get_cell(
        self,
        dat: Any,
        row: int,
        col_name: str,
        default: Any = ''
    ) -> Any:
        """
        Safely get a cell value from the DAT.

        Tries by column name first, then by index.
        """
        try:
            # Try by column name
            value = dat[row, col_name]
            return str(value) if value is not None else default
        except:
            pass

        try:
            # Try by column index
            col_idx = ERROR_DAT_COLUMNS.get(col_name, 0)
            value = dat[row, col_idx]
            return str(value) if value is not None else default
        except:
            return default

    def clear_errors(self) -> Result:
        """
        Clear all errors from the Error DAT.

        Note: This may not work on all Error DAT configurations.
        """
        try:
            error_dat = self._find_error_dat()

            if error_dat is None:
                return {
                    'success': False,
                    'error': "No Error DAT found"
                }

            # Attempt to clear (may require write access)
            if hasattr(error_dat, 'clear'):
                error_dat.clear()
                log_message("Cleared Error DAT", LogLevel.INFO)
                return {'success': True, 'data': {'cleared': True}}

            return {
                'success': False,
                'error': "Error DAT does not support clearing"
            }

        except Exception as e:
            return {
                'success': False,
                'error': f"Exception clearing errors: {str(e)}"
            }

    def get_error_summary(self) -> Result:
        """
        Get a summary of errors by severity level.

        Returns counts and most recent error per severity.
        """
        result = self.get_cook_errors(limit=1000)

        if not result.get('success'):
            return result

        errors = result.get('data', {}).get('errors', [])

        summary = {
            'info': {'count': 0, 'latest': None},
            'warning': {'count': 0, 'latest': None},
            'error': {'count': 0, 'latest': None},
            'fatal': {'count': 0, 'latest': None},
        }

        for error in errors:
            severity = error.get('severity', 'info')
            if severity in summary:
                summary[severity]['count'] += 1
                # Keep track of latest (highest absframe)
                if summary[severity]['latest'] is None:
                    summary[severity]['latest'] = error
                elif error.get('absframe', 0) > summary[severity]['latest'].get('absframe', 0):
                    summary[severity]['latest'] = error

        return {
            'success': True,
            'data': {
                'summary': summary,
                'total_count': len(errors)
            }
        }

    def get_python_exceptions(self, limit: int = 50) -> Result:
        """
        Get Python-specific exceptions from the Error DAT.

        Filters errors to only return those from Python scripts,
        which typically have type containing 'python' or 'script'.

        Args:
            limit: Maximum number of exceptions to return

        Returns:
            Result containing:
            - exceptions: list of Python-related errors
            - total_count: number of Python exceptions found
        """
        try:
            error_dat = self._find_error_dat()

            if error_dat is None:
                log_message("No Error DAT found for Python exceptions", LogLevel.WARNING)
                return {
                    'success': True,
                    'data': {
                        'exceptions': [],
                        'total_count': 0,
                        'note': 'No Error DAT found'
                    }
                }

            num_rows = error_dat.numRows
            if num_rows <= 1:
                return {
                    'success': True,
                    'data': {
                        'exceptions': [],
                        'total_count': 0,
                        'note': 'Error DAT is empty'
                    }
                }

            exceptions = []
            for row_idx in range(1, num_rows):
                if len(exceptions) >= limit:
                    break

                try:
                    op_type = self._get_cell(error_dat, row_idx, 'type', default='').lower()
                    message = self._get_cell(error_dat, row_idx, 'message', default='')

                    # Filter for Python-related errors
                    is_python = (
                        'python' in op_type or
                        'script' in op_type or
                        'dat' in op_type or
                        'Traceback' in message or
                        'Error:' in message or
                        'Exception' in message
                    )

                    if is_python:
                        source = self._get_cell(error_dat, row_idx, 'source')
                        frame = self._get_cell(error_dat, row_idx, 'frame', default=0)
                        absframe = self._get_cell(error_dat, row_idx, 'absframe', default=0)
                        severity_raw = self._get_cell(error_dat, row_idx, 'severity', default=0)
                        severity = SEVERITY_MAP.get(severity_raw, 'error')

                        exceptions.append({
                            'source': source,
                            'message': message,
                            'type': op_type,
                            'frame': int(frame) if frame else 0,
                            'absframe': int(absframe) if absframe else 0,
                            'severity': severity,
                        })

                except Exception as row_error:
                    log_message(f"Error parsing Python exception row {row_idx}: {str(row_error)}", LogLevel.WARNING)
                    continue

            log_message(f"Found {len(exceptions)} Python exceptions", LogLevel.INFO)

            return {
                'success': True,
                'data': {
                    'exceptions': exceptions,
                    'total_count': len(exceptions)
                }
            }

        except Exception as e:
            log_message(f"Error getting Python exceptions: {str(e)}", LogLevel.ERROR)
            return {
                'success': False,
                'error': f"Exception getting Python exceptions: {str(e)}"
            }


# Singleton instance for use by controllers
error_monitor = ErrorMonitorService()
