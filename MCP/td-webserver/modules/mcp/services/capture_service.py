"""
Capture Service for Network Editor MCP
Provides visual feedback by capturing TOP operator outputs as images.

Part of Phase 1 POC for TD Builder visual feedback integration.
Author: FELIX (Feature Engineer)
Date: 2024-12-25n"""

import base64
from typing import Any, Optional

import td
from utils.logging import log_message
from utils.types import LogLevel, Result

# W-B — temp op-viewer node name, keyed PER TARGET OP (prefix + the target's own
# name). Rationale: the two-phase capture spans two HTTP requests with a client-side
# wait between them, so a primed viewer stays alive across that gap. A single
# per-parent name let a second capture of a SIBLING op (same parent, overlapping the
# gap) destroy+recreate the node under the same path; the first capture's phase-2
# pull then resolved the sibling's viewer and returned the WRONG operator's image,
# still labeled with the first op's path (silent cross-wire — TD's single request
# thread does NOT close this window, it only makes each request atomic). Keying the
# name to the target op makes each capture's node path unique per target within its
# parent (op names are unique among siblings), so a handle can only ever resolve to
# a viewer of the SAME op — or to nothing (a clean "handle not found" error), never
# to a different op's viewer. The stale-viewer self-heal still holds per target: a
# leaked viewer for op X is cleaned up by the next prime of X (same name).
_TEMP_VIEWER_PREFIX = "temp_opviewer_capture_"


def _temp_viewer_name(target_op) -> str:
    """Per-target temp op-viewer node name (see ``_TEMP_VIEWER_PREFIX``)."""
    name = getattr(target_op, "name", "") or "op"
    return f"{_TEMP_VIEWER_PREFIX}{name}"

# Phase-2 pull retry ceiling. All pulls in one HTTP request share a frame; this only
# rides out within-frame progressive growth (we are already >=1 frame past prime),
# and we stop as soon as the byte size stabilizes (size-stability, not a threshold).
_PULL_MAX_ATTEMPTS = 6


class CaptureService:
    """
    Service for capturing visual output from TouchDesigner operators.

    Provides:
    - TOP operator screenshot capture as base64 JPEG/PNG
    - Resolution metadata for captured images
    """

    def __init__(self):
        log_message("CaptureService initialized", LogLevel.INFO)

    def capture_top_output(
        self,
        operator_path: str,
        resolution: str = "original",
        format: str = "jpeg",
        quality: float = 0.85
    ) -> Result:
        """
        Capture a TOP operator's rendered output as a base64-encoded image.

        Args:
            operator_path: Full path to the TOP operator (e.g., "/project1/null1")
            resolution: Target resolution - "original", "256", "512", or "1024"
            format: Image format - "jpeg" (smaller, lossy) or "png" (larger, lossless)
            quality: JPEG quality 0.0-1.0 (ignored for PNG)

        Returns:
            Result containing:
            - success: bool
            - data: {image_base64, width, height, format} on success
            - error: error message on failure
        """
        try:
            log_message(f"Capturing TOP output: {operator_path} (format={format}, quality={quality})", LogLevel.INFO)

            # Get reference to the TOP operator
            top_op = td.op(operator_path)

            if top_op is None:
                return {
                    'success': False,
                    'error': f"Operator not found: {operator_path}"
                }

            # Verify it's a TOP
            if not hasattr(top_op, 'saveByteArray'):
                return {
                    'success': False,
                    'error': f"Operator is not a TOP (no saveByteArray method): {operator_path}"
                }

            # Get original dimensions
            width = top_op.width
            height = top_op.height

            if width == 0 or height == 0:
                return {
                    'success': False,
                    'error': f"TOP has zero dimensions ({width}x{height}): {operator_path}"
                }

            # Force cook to ensure latest output
            top_op.cook(force=True)

            # Determine format and quality settings
            if format.lower() == 'png':
                file_ext = '.png'
                img_quality = 1.0  # PNG ignores quality
                mime_format = 'png'
            else:
                file_ext = '.jpg'
                # Clamp quality to valid range
                img_quality = max(0.1, min(1.0, quality))
                mime_format = 'jpeg'

            # Capture to bytearray
            # saveByteArray(filetype, quality=1.0, metadata=[])
            img_bytes = top_op.saveByteArray(file_ext, quality=img_quality)

            if img_bytes is None or len(img_bytes) == 0:
                return {
                    'success': False,
                    'error': f"Failed to capture image from TOP: {operator_path}"
                }

            # Base64 encode for JSON transport
            image_base64 = base64.b64encode(img_bytes).decode('utf-8')

            log_message(
                f"Captured {width}x{height} {mime_format.upper()} ({len(img_bytes)} bytes raw, {len(image_base64)} bytes b64) from {operator_path}",
                LogLevel.INFO
            )

            return {
                'success': True,
                'data': {
                    'image_base64': image_base64,
                    'width': width,
                    'height': height,
                    'format': mime_format,
                    'operator_path': operator_path,
                    'bytes_raw': len(img_bytes),
                    'bytes_base64': len(image_base64)
                }
            }

        except Exception as e:
            log_message(f"Error capturing TOP: {str(e)}", LogLevel.ERROR)
            return {
                'success': False,
                'error': f"Exception during capture: {str(e)}"
            }

    def get_top_info(self, operator_path: str) -> Result:
        """
        Get information about a TOP operator without capturing its output.

        Useful for checking if a TOP exists and its current state before capture.

        Args:
            operator_path: Full path to the TOP operator

        Returns:
            Result containing TOP metadata (width, height, format, cook state)
        """
        try:
            top_op = td.op(operator_path)

            if top_op is None:
                return {
                    'success': False,
                    'error': f"Operator not found: {operator_path}"
                }

            if not hasattr(top_op, 'width'):
                return {
                    'success': False,
                    'error': f"Operator is not a TOP: {operator_path}"
                }

            return {
                'success': True,
                'data': {
                    'operator_path': operator_path,
                    'width': top_op.width,
                    'height': top_op.height,
                    'aspect': top_op.aspect if hasattr(top_op, 'aspect') else None,
                    'pixel_format': str(top_op.pixelFormat) if hasattr(top_op, 'pixelFormat') else None,
                    'gpu_memory': top_op.gpuMemory if hasattr(top_op, 'gpuMemory') else None,
                    'cook_time': top_op.cookTime if hasattr(top_op, 'cookTime') else None,
                }
            }

        except Exception as e:
            log_message(f"Error getting TOP info: {str(e)}", LogLevel.ERROR)
            return {
                'success': False,
                'error': f"Exception getting TOP info: {str(e)}"
            }

    def capture_network_layout(self, comp_path: str, depth: int = 1) -> Result:
        """
        Get network graph data (nodes + connections) for a COMP.

        Returns structured data about operator positions and connections,
        which can be used for visualization or analysis.

        Args:
            comp_path: Path to the COMP (e.g., "/project1")
            depth: How deep to search for children (default 1 = direct children)

        Returns:
            Result containing:
            - nodes: list of {name, path, type, family, x, y}
            - connections: list of {from_path, to_path, to_input}
            - node_count, connection_count
        """
        try:
            log_message(f"Capturing network layout: {comp_path}", LogLevel.INFO)

            comp = td.op(comp_path)
            if comp is None:
                return {
                    'success': False,
                    'error': f"COMP not found: {comp_path}"
                }

            # Verify it's a COMP (has children)
            if not hasattr(comp, 'findChildren'):
                return {
                    'success': False,
                    'error': f"Operator is not a COMP: {comp_path}"
                }

            nodes = []
            connections = []

            # Collect all child nodes.
            # B14 — `depth=N` is exact-depth in TD (only nodes at level N);
            # `maxDepth=N` is inclusive (levels 1..N). The tool's contract is inclusive.
            children = comp.findChildren(maxDepth=depth)
            for child in children:
                node_info = {
                    'name': child.name,
                    'path': child.path,
                    'type': child.OPType if hasattr(child, 'OPType') else str(type(child).__name__),
                    'family': child.family if hasattr(child, 'family') else '',
                    'x': child.nodeX if hasattr(child, 'nodeX') else 0,
                    'y': child.nodeY if hasattr(child, 'nodeY') else 0,
                }
                nodes.append(node_info)

            # Collect connections between nodes
            for child in children:
                if hasattr(child, 'inputs'):
                    for i, input_op in enumerate(child.inputs):
                        if input_op is not None:
                            # Only include connections within this COMP
                            if hasattr(input_op, 'parent') and input_op.parent() == comp:
                                connections.append({
                                    'from_path': input_op.path,
                                    'to_path': child.path,
                                    'to_input': i,
                                })

            log_message(
                f"Captured network layout: {len(nodes)} nodes, {len(connections)} connections",
                LogLevel.INFO
            )

            return {
                'success': True,
                'data': {
                    'comp_path': comp_path,
                    'nodes': nodes,
                    'connections': connections,
                    'node_count': len(nodes),
                    'connection_count': len(connections),
                }
            }

        except Exception as e:
            log_message(f"Error capturing network layout: {str(e)}", LogLevel.ERROR)
            return {
                'success': False,
                'error': f"Exception capturing network layout: {str(e)}"
            }


    # =========================================================================
    # Phase 3: Universal Op Viewer
    # =========================================================================

    def capture_op_viewer(
        self,
        operator_path: str,
        resolution: int = 512,
        format: str = "jpeg",
        quality: float = 0.85,
        prime_only: bool = False,
    ) -> Result:
        """
        Capture ANY operator's viewer as an image (Universal Op Viewer).

        Uses OP Viewer TOP internally to capture the node viewer for any operator type.
        For DATs, returns text content instead of an image.

        W-B — the opviewerTOP render is PROGRESSIVE and needs a real frame boundary:
        pulled in the same frame it is wired, it only ever returns the blank/partial
        plateau (proven: 2 KB background, 7.5 KB axes; a POP point cloud never
        appears). So the op-viewer branch is a TWO-PHASE capture split across two MCP
        HTTP requests with a client-side (never TD-side) wait between them:
          * ``prime_only=True``  -> create+wire the temp viewer, prime it with one
            pull, return a handle (NO image). See ``_prime_op_viewer``.
          * ``pull_op_viewer(handle, ...)`` (a SECOND request, ~1 frame later) ->
            force-cook + saveByteArray, retry to size-stability, destroy the viewer.
        The direct families (TOP/DAT/CHOP/SOP) return their full result on the prime
        request (``two_phase`` absent), so the client renders them without a wait.

        Args:
            operator_path: Full path to any operator
            resolution: Output resolution (width in pixels)
            format: Image format - "jpeg" or "png"
            quality: JPEG quality 0.1-1.0
            prime_only: op-viewer branch only — prime + return a handle (phase 1)
                instead of the legacy same-frame single-shot capture.

        Returns:
            Result containing:
            - For image: {type: 'image', image_base64, width, height, format, family}
            - For a primed viewer: {type: 'op_viewer_primed', two_phase: True, handle}
            - For text: {type: 'text', content, rows, cols, family}
        """
        try:
            log_message(f"Capturing op viewer: {operator_path} (prime_only={prime_only})", LogLevel.INFO)

            target_op = td.op(operator_path)

            if target_op is None:
                return {'success': False, 'error': f"Operator not found: {operator_path}"}

            family = target_op.family if hasattr(target_op, 'family') else 'unknown'
            op_type = target_op.OPType if hasattr(target_op, 'OPType') else 'unknown'

            log_message(f"Operator family: {family}, type: {op_type}", LogLevel.DEBUG)

            if family == 'TOP':
                return self._capture_top_direct(target_op, format, quality)
            elif family == 'DAT':
                return self._capture_dat_data(target_op)
            elif family == 'CHOP':
                return self._capture_chop_data(target_op)
            elif family == 'SOP':
                return self._capture_sop_info(target_op)
            else:
                # POP / MAT / COMP / unknown -> op-viewer render (two-phase capable).
                if prime_only:
                    return self._prime_op_viewer(target_op, resolution, format)
                # Legacy single-shot (kept for direct / no-phase HTTP callers). A POP
                # will under-render here (no frame boundary); the MCP client always
                # uses the two-phase path. POP info is merged either way.
                result = self._capture_via_opviewer(target_op, resolution, format, quality)
                if family == 'POP' and result.get('success') and isinstance(result.get('data'), dict):
                    self._merge_pop_info(result['data'], target_op)
                return result

        except Exception as e:
            log_message(f"Error in capture_op_viewer: {str(e)}", LogLevel.ERROR)
            return {'success': False, 'error': f"Exception in capture_op_viewer: {str(e)}"}

    def _capture_top_direct(self, top_op, format: str, quality: float) -> Result:
        """Capture a TOP directly using saveByteArray."""
        try:
            width, height = top_op.width, top_op.height
            if width == 0 or height == 0:
                return {'success': False, 'error': f"TOP has zero dimensions: {top_op.path}"}

            top_op.cook(force=True)

            if format.lower() == 'png':
                file_ext, img_quality, mime_format = '.png', 1.0, 'png'
            else:
                file_ext, img_quality, mime_format = '.jpg', max(0.1, min(1.0, quality)), 'jpeg'

            img_bytes = top_op.saveByteArray(file_ext, quality=img_quality)
            if img_bytes is None or len(img_bytes) == 0:
                return {'success': False, 'error': f"Failed to capture TOP: {top_op.path}"}

            image_base64 = base64.b64encode(img_bytes).decode('utf-8')
            return {
                'success': True,
                'data': {
                    'type': 'image', 'image_base64': image_base64,
                    'width': width, 'height': height, 'format': mime_format,
                    'family': 'TOP', 'operator_path': top_op.path, 'bytes_raw': len(img_bytes)
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _capture_dat_data(self, dat_op) -> Result:
        """Capture a DAT's data - text content and table structure."""
        try:
            rows = dat_op.numRows if hasattr(dat_op, 'numRows') else 0
            cols = dat_op.numCols if hasattr(dat_op, 'numCols') else 0
            
            # Get text content
            text_content = dat_op.text if hasattr(dat_op, 'text') else ''
            
            # Build table data if it's a table DAT
            table_data = None
            if rows > 0 and cols > 0:
                table_data = []
                max_rows = min(rows, 100)  # Limit to 100 rows
                for r in range(max_rows):
                    row_data = []
                    for c in range(cols):
                        try:
                            cell = dat_op[r, c].val if dat_op[r, c] else ''
                            row_data.append(str(cell))
                        except:
                            row_data.append('')
                    table_data.append(row_data)
            
            return {
                'success': True,
                'data': {
                    'type': 'dat_data',
                    'family': 'DAT',
                    'operator_path': dat_op.path,
                    'dat_type': dat_op.OPType if hasattr(dat_op, 'OPType') else 'unknown',
                    'rows': rows,
                    'cols': cols,
                    'text': text_content[:5000] if len(text_content) > 5000 else text_content,
                    'table': table_data,
                    'truncated': len(text_content) > 5000 or rows > 100
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _capture_chop_data(self, chop_op) -> Result:
        """Capture a CHOP's channel data."""
        try:
            num_chans = chop_op.numChans if hasattr(chop_op, 'numChans') else 0
            num_samples = chop_op.numSamples if hasattr(chop_op, 'numSamples') else 0
            sample_rate = chop_op.rate if hasattr(chop_op, 'rate') else 0
            
            # Build channel info
            channels = []
            for i in range(num_chans):
                try:
                    chan = chop_op[i]
                    chan_info = {
                        'name': chan.name,
                        'index': i,
                        'current_value': chan.eval(),
                    }
                    # Get min/max if we have samples
                    if num_samples > 0:
                        vals = [chan[s] for s in range(min(num_samples, 1000))]
                        chan_info['min'] = min(vals)
                        chan_info['max'] = max(vals)
                        chan_info['avg'] = sum(vals) / len(vals)
                        # Include sample data for small CHOPs
                        if num_samples <= 100:
                            chan_info['samples'] = vals
                    channels.append(chan_info)
                except Exception as e:
                    channels.append({'name': f'chan{i}', 'error': str(e)})
            
            return {
                'success': True,
                'data': {
                    'type': 'chop_data',
                    'family': 'CHOP',
                    'operator_path': chop_op.path,
                    'chop_type': chop_op.OPType if hasattr(chop_op, 'OPType') else 'unknown',
                    'num_channels': num_chans,
                    'num_samples': num_samples,
                    'sample_rate': sample_rate,
                    'channels': channels
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _capture_via_opviewer(self, target_op, resolution: int, format: str, quality: float) -> Result:
        """Capture any operator using a temporary OP Viewer TOP."""
        temp_viewer = None
        try:
            parent = target_op.parent()
            family = target_op.family if hasattr(target_op, 'family') else 'unknown'

            temp_viewer = parent.create('opviewerTOP', _temp_viewer_name(target_op))
            temp_viewer.par.opviewer = target_op.path
            temp_viewer.par.resolutionw = resolution
            temp_viewer.par.resolutionh = resolution
            temp_viewer.cook(force=True)

            width, height = temp_viewer.width, temp_viewer.height
            if width == 0 or height == 0:
                return {'success': False, 'error': f"OP Viewer zero dimensions: {target_op.path}"}

            if format.lower() == 'png':
                file_ext, img_quality, mime_format = '.png', 1.0, 'png'
            else:
                file_ext, img_quality, mime_format = '.jpg', max(0.1, min(1.0, quality)), 'jpeg'

            img_bytes = temp_viewer.saveByteArray(file_ext, quality=img_quality)
            if img_bytes is None or len(img_bytes) == 0:
                return {'success': False, 'error': f"Failed via OP Viewer: {target_op.path}"}

            image_base64 = base64.b64encode(img_bytes).decode('utf-8')
            log_message(f"Captured {width}x{height} {mime_format} via OP Viewer for {family}: {target_op.path}", LogLevel.INFO)

            return {
                'success': True,
                'data': {
                    'type': 'image', 'image_base64': image_base64,
                    'width': width, 'height': height, 'format': mime_format,
                    'family': family, 'operator_path': target_op.path, 'bytes_raw': len(img_bytes)
                }
            }
        except Exception as e:
            log_message(f"Error in _capture_via_opviewer: {str(e)}", LogLevel.ERROR)
            return {'success': False, 'error': str(e)}
        finally:
            if temp_viewer is not None:
                try:
                    temp_viewer.destroy()
                except:
                    pass

    def _prime_op_viewer(self, target_op, resolution: int, format: str) -> Result:
        """Phase 1 of the two-phase capture: create+wire the temp OP Viewer TOP and
        prime it with one pull, returning a handle. Does NOT destroy — phase 2
        (``pull_op_viewer``) owns cleanup. On any error BEFORE a handle is returned
        the temp viewer is destroyed here so nothing leaks."""
        temp_viewer = None
        try:
            parent = target_op.parent()
            family = target_op.family if hasattr(target_op, 'family') else 'unknown'
            viewer_name = _temp_viewer_name(target_op)

            # Clean up a viewer for THIS target leaked by a prior aborted call so
            # create() does not auto-suffix (which would strand THIS one under a
            # different name). Scoped to the per-target name so we never destroy a
            # sibling capture's in-flight primed viewer (the cross-wire we fixed).
            stale = parent.op(viewer_name)
            if stale is not None and getattr(stale, 'valid', False):
                try:
                    stale.destroy()
                except Exception:
                    pass

            temp_viewer = parent.create('opviewerTOP', viewer_name)
            temp_viewer.par.opviewer = target_op.path
            temp_viewer.par.resolutionw = resolution
            temp_viewer.par.resolutionh = resolution
            try:
                temp_viewer.nodeX, temp_viewer.nodeY = target_op.nodeX, target_op.nodeY - 150
            except Exception:
                pass

            # Prime pull — kicks off the progressive render; the real frame boundary
            # happens during the client's wait before the phase-2 pull.
            temp_viewer.cook(force=True)
            primed_bytes = None
            try:
                file_ext = '.png' if format.lower() == 'png' else '.jpg'
                primed = temp_viewer.saveByteArray(file_ext)
                primed_bytes = len(primed) if primed else 0
            except Exception:
                primed_bytes = None

            return {
                'success': True,
                'data': {
                    'type': 'op_viewer_primed',
                    'two_phase': True,
                    'handle': temp_viewer.path,
                    'operator_path': target_op.path,
                    'family': family,
                    'primed_bytes': primed_bytes,
                }
            }
        except Exception as e:
            log_message(f"Error in _prime_op_viewer: {str(e)}", LogLevel.ERROR)
            # No handle was returned to the client -> destroy so nothing leaks.
            if temp_viewer is not None:
                try:
                    temp_viewer.destroy()
                except Exception:
                    pass
            return {'success': False, 'error': str(e)}

    def pull_op_viewer(
        self,
        handle: str,
        operator_path: str = "",
        format: str = "jpeg",
        quality: float = 0.85,
    ) -> Result:
        """Phase 2 of the two-phase capture: pull the primed viewer to a stable byte
        size and encode it, then DESTROY the temp viewer in a finally-equivalent
        (leak-proof, including on error). ``operator_path`` is the ORIGINAL op — used
        to attach the POP numPoints/bounds sidecar and report family."""
        temp_viewer = td.op(handle) if handle else None
        try:
            if temp_viewer is None or not getattr(temp_viewer, 'valid', False):
                return {'success': False, 'error': f"Temp viewer handle not found: {handle}"}

            if format.lower() == 'png':
                file_ext, img_quality, mime_format = '.png', 1.0, 'png'
            else:
                file_ext, img_quality, mime_format = '.jpg', max(0.1, min(1.0, quality)), 'jpeg'

            # Pull until the byte size stabilizes (progressive render converged).
            best = b''
            sizes = []
            for _ in range(_PULL_MAX_ATTEMPTS):
                temp_viewer.cook(force=True)
                chunk = temp_viewer.saveByteArray(file_ext, quality=img_quality) or b''
                sizes.append(len(chunk))
                if len(chunk) > len(best):
                    best = chunk
                # Two equal, non-zero pulls in a row => converged; stop.
                if len(sizes) >= 2 and sizes[-1] == sizes[-2] and sizes[-1] > 0:
                    break

            if not best:
                return {'success': False, 'error': f"OP Viewer produced no bytes: {operator_path or handle}"}

            width, height = temp_viewer.width, temp_viewer.height
            image_base64 = base64.b64encode(best).decode('utf-8')

            family = 'unknown'
            data = {
                'type': 'image',
                'image_base64': image_base64,
                'width': width,
                'height': height,
                'format': mime_format,
                'operator_path': operator_path or handle,
                'bytes_raw': len(best),
                'two_phase': True,
                'pulls': len(sizes),
                'pull_sizes': sizes,
            }

            orig = td.op(operator_path) if operator_path else None
            if orig is not None and getattr(orig, 'valid', False):
                family = orig.family if hasattr(orig, 'family') else 'unknown'
                if family == 'POP':
                    self._merge_pop_info(data, orig)
            data['family'] = family

            log_message(
                f"Two-phase capture of {family} {operator_path or handle}: "
                f"{width}x{height}, {len(best)} bytes over {len(sizes)} pull(s) {sizes}",
                LogLevel.INFO,
            )
            return {'success': True, 'data': data}
        except Exception as e:
            log_message(f"Error in pull_op_viewer: {str(e)}", LogLevel.ERROR)
            return {'success': False, 'error': str(e)}
        finally:
            if temp_viewer is not None:
                try:
                    temp_viewer.destroy()
                except Exception:
                    pass

    def _capture_pop_info(self, pop_op) -> Result:
        """POP geometry info sidecar (clone of ``_capture_sop_info``).

        Report L9 — a POP capture should carry numPoints + bounds so the caller can
        verify a point cloud without a second ``poptoCHOP`` round-trip. Every read is
        hasattr/try-guarded: if a given TD POP build does not expose an attribute the
        field is simply omitted (needs live confirmation of the exact attr names).
        """
        try:
            num_points = pop_op.numPoints if hasattr(pop_op, 'numPoints') else 0

            bounds = None
            if hasattr(pop_op, 'pointBoundingBox'):
                try:
                    bbox = pop_op.pointBoundingBox
                    bounds = {
                        'min': [bbox.min.x, bbox.min.y, bbox.min.z],
                        'max': [bbox.max.x, bbox.max.y, bbox.max.z],
                        'center': [bbox.center.x, bbox.center.y, bbox.center.z],
                        'size': [bbox.size.x, bbox.size.y, bbox.size.z],
                    }
                except Exception:
                    pass

            return {
                'success': True,
                'data': {
                    'type': 'geometry_info', 'family': 'POP', 'operator_path': pop_op.path,
                    'num_points': num_points, 'bounds': bounds,
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _merge_pop_info(self, data: dict, pop_op) -> None:
        """Merge the POP numPoints/bounds sidecar into an image-capture data dict."""
        info = self._capture_pop_info(pop_op)
        if info.get('success') and isinstance(info.get('data'), dict):
            d = info['data']
            data['num_points'] = d.get('num_points')
            if d.get('bounds') is not None:
                data['bounds'] = d['bounds']

    def _capture_sop_info(self, sop_op) -> Result:
        """Return info about a SOP (full render chain is Phase 3.3)."""
        try:
            num_points = sop_op.numPoints if hasattr(sop_op, 'numPoints') else 0
            num_prims = sop_op.numPrims if hasattr(sop_op, 'numPrims') else 0
            num_vertices = sop_op.numVertices if hasattr(sop_op, 'numVertices') else 0

            bounds = None
            if hasattr(sop_op, 'pointBoundingBox'):
                try:
                    bbox = sop_op.pointBoundingBox
                    bounds = {
                        'min': [bbox.min.x, bbox.min.y, bbox.min.z],
                        'max': [bbox.max.x, bbox.max.y, bbox.max.z],
                        'center': [bbox.center.x, bbox.center.y, bbox.center.z],
                        'size': [bbox.size.x, bbox.size.y, bbox.size.z]
                    }
                except:
                    pass

            return {
                'success': True,
                'data': {
                    'type': 'geometry_info', 'family': 'SOP', 'operator_path': sop_op.path,
                    'num_points': num_points, 'num_prims': num_prims, 'num_vertices': num_vertices,
                    'bounds': bounds, 'note': 'Full SOP rendering coming in Phase 3.3'
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Singleton instance for use by controllers
capture_service = CaptureService()

