/**
 * API client layer for Calispec AI Search, Secure RBAC, & Private Dataset Management
 */
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const AUTH_TOKEN_KEY = 'calispec_auth_token';
const AUTH_USER_KEY = 'calispec_auth_user';

/**
 * Returns currently stored JWT access token from localStorage.
 */
export function getAuthToken() {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * Persists user session and token in localStorage.
 */
export function setAuthSession(token, user) {
  try {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
    if (user) {
      localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
    }
  } catch (e) {
    console.error('Error saving session:', e);
  }
}

/**
 * Retrieves cached user object from localStorage.
 */
export function getStoredUser() {
  try {
    const raw = localStorage.getItem(AUTH_USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/**
 * Clears stored auth tokens and user profile.
 */
export function clearAuthSession() {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(AUTH_USER_KEY);
  } catch (e) {
    console.error('Error clearing session:', e);
  }
}

/**
 * Helper to inject Authorization Bearer header.
 */
function getAuthHeaders(extraHeaders = {}) {
  const token = getAuthToken();
  const headers = { ...extraHeaders };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

/**
 * Authenticates an authorized user with email and password.
 * @param {string} email 
 * @param {string} password 
 * @returns {Promise<{access_token: string, user: {user_id: string, email: string, role: string}}>}
 */
export async function loginApi(email, password) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email: email.trim(), password }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.detail || 'Authentication failed. Please verify credentials.');
    }

    const data = await response.json();
    setAuthSession(data.access_token, data.user);
    return data;
  } catch (error) {
    console.error('loginApi error:', error);
    throw error;
  }
}

/**
 * Validates the stored token and fetches the fresh user profile from backend.
 * Returns null if unauthenticated.
 */
export async function fetchCurrentUser() {
  const token = getAuthToken();
  if (!token) return null;

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      clearAuthSession();
      return null;
    }

    const user = await response.json();
    setAuthSession(token, user);
    return user;
  } catch (error) {
    console.error('fetchCurrentUser error:', error);
    return null;
  }
}

/**
 * Logs out user from backend session.
 */
export async function logoutApi() {
  try {
    await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: 'POST',
      headers: getAuthHeaders(),
    }).catch(() => null);
  } finally {
    clearAuthSession();
  }
}

/**
 * Sends a search query to the /api/chat endpoint.
 * @param {string} message 
 * @param {string|null} [datasetId] 
 * @returns {Promise<{success: boolean, found: boolean, count: number, dataset_id?: string, dataset_name?: string, data: any, query_intent?: any, message?: string}>}
 */
export async function sendChatMessage(message, datasetId = null) {
  try {
    const payload = { message };
    if (datasetId && datasetId !== 'default' && datasetId !== 'all') {
      payload.dataset_id = datasetId;
    } else {
      payload.dataset_id = 'all';
    }

    const response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: 'POST',
      headers: getAuthHeaders({
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.detail || `Server responded with status ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('API sendChatMessage error:', error);
    throw error;
  }
}

/**
 * Direct search endpoint bypassing LLM parsing.
 * @param {string} query 
 * @param {string} [field] 
 * @param {string|null} [datasetId]
 */
export async function sendDirectSearch(query, field = '', datasetId = null) {
  try {
    const params = new URLSearchParams({ q: query });
    if (field) {
      params.append('field', field);
    }
    if (datasetId && datasetId !== 'default' && datasetId !== 'all') {
      params.append('dataset_id', datasetId);
    } else {
      params.append('dataset_id', 'all');
    }
    const response = await fetch(`${API_BASE_URL}/api/search?${params.toString()}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(`Server responded with status ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error('API sendDirectSearch error:', error);
    throw error;
  }
}

/**
 * Uploads a file (.csv, .xlsx, .xls, .json, .xml, .txt) to MongoDB.
 * Protected: Requires DATA_UPLOADER role.
 * @param {File} file 
 * @param {string|null} [sheetName] 
 * @returns {Promise<{success: boolean, dataset_id: string, filename: string, record_count: number, fields: string[], normalized_fields?: string[], message: string}>}
 */
export async function uploadDatasetFile(file, sheetName = null) {
  try {
    const formData = new FormData();
    formData.append('file', file);
    if (sheetName) {
      formData.append('sheet_name', sheetName);
    }

    const response = await fetch(`${API_BASE_URL}/api/datasets/upload`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.detail || `Upload failed with status ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('API uploadDatasetFile error:', error);
    throw error;
  }
}

/**
 * Inspects a file before upload (for multi-sheet Excel files or pre-upload schema preview).
 * Protected: Requires DATA_UPLOADER role.
 * @param {File} file 
 * @param {string|null} [sheetName] 
 */
export async function inspectDatasetFile(file, sheetName = null) {
  try {
    const formData = new FormData();
    formData.append('file', file);
    if (sheetName) {
      formData.append('sheet_name', sheetName);
    }

    const response = await fetch(`${API_BASE_URL}/api/datasets/inspect`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.detail || `Inspection failed with status ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('API inspectDatasetFile error:', error);
    throw error;
  }
}

/**
 * Uploads a file for offline deterministic cleaning & preview report.
 * Protected: Requires DATA_UPLOADER role.
 * @param {File} file 
 */
export async function previewDatasetFile(file) {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/api/datasets/upload/preview`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.detail || `Preview failed with status ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('API previewDatasetFile error:', error);
    throw error;
  }
}

/**
 * Downloads the Excel audit report for an active preview.
 * @param {string} previewId 
 * @param {string} filename 
 */
export async function downloadReportExcel(previewId, filename = 'cleaning_report.xlsx') {
  try {
    const response = await fetch(`${API_BASE_URL}/api/datasets/upload/preview/${previewId}/report.xlsx`, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.detail || 'Failed to download Excel report.');
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename.endsWith('.xlsx') ? filename : `${filename}_report.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('API downloadReportExcel error:', error);
    throw error;
  }
}

/**
 * Fetches paginated changes for an active preview.
 * @param {string} previewId
 * @param {number} [offset=0]
 * @param {number} [limit=100]
 * @param {string} [action='']
 * @returns {Promise<{success: boolean, total: number, offset: number, limit: number, changes: Array}>}
 */
export async function fetchPreviewChanges(previewId, offset = 0, limit = 100, action = '') {
  try {
    const params = new URLSearchParams({
      offset: String(offset),
      limit: String(limit),
    });
    if (action && action !== 'all') {
      params.append('action', action);
    }
    const response = await fetch(`${API_BASE_URL}/api/datasets/upload/preview/${previewId}/changes?${params.toString()}`, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.detail || `Failed to fetch changes: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('API fetchPreviewChanges error:', error);
    throw error;
  }
}

/**
 * Confirms saving cleaned records to MongoDB, or re-cleans if custom column mapping is provided.
 * @param {string} previewId 
 * @param {string} datasetName 
 * @param {'append'|'replace'} mode 
 * @param {Object|null} [columnMapping] 
 */
export async function confirmDatasetUpload(previewId, datasetName = '', mode = 'append', columnMapping = null) {
  try {
    const payload = {
      preview_id: previewId,
      dataset_name: datasetName || null,
      mode: mode,
    };
    if (columnMapping) {
      payload.column_mapping = columnMapping;
    }

    const response = await fetch(`${API_BASE_URL}/api/datasets/upload/confirm`, {
      method: 'POST',
      headers: getAuthHeaders({
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => null);
      throw new Error(errData?.detail || `Confirm failed with status ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('API confirmDatasetUpload error:', error);
    throw error;
  }
}

/**
 * Cancels preview and frees in-memory bytes on backend.
 * @param {string} previewId 
 */
export async function cancelDatasetUpload(previewId) {
  try {
    await fetch(`${API_BASE_URL}/api/datasets/upload/cancel`, {
      method: 'POST',
      headers: getAuthHeaders({
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify({ preview_id: previewId }),
    }).catch(() => null);
  } catch (error) {
    console.warn('API cancelDatasetUpload error:', error);
  }
}


/**
 * Fetches list of all uploaded datasets from MongoDB.
 */
export async function fetchDatasets() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/datasets`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) return { success: true, count: 0, datasets: [] };
    return await response.json();
  } catch (error) {
    console.error('API fetchDatasets error:', error);
    return { success: false, count: 0, datasets: [] };
  }
}

/**
 * Fetches metadata and sample records for a specific dataset.
 * @param {string} datasetId 
 */
export async function fetchDatasetDetails(datasetId) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) return null;
    return await response.json();
  } catch (error) {
    console.error('API fetchDatasetDetails error:', error);
    return null;
  }
}

/**
 * Deletes an uploaded dataset and its records from MongoDB.
 * Protected: Requires DATA_UPLOADER role.
 * @param {string} datasetId 
 */
export async function deleteDatasetApi(datasetId) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.detail || 'Delete failed');
    }
    return await response.json();
  } catch (error) {
    console.error('API deleteDatasetApi error:', error);
    throw error;
  }
}

/**
 * Checks system health and MongoDB connectivity.
 */
export async function checkBackendHealth() {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    if (!response.ok) return { status: 'error', database_connected: false, total_uploaded_datasets: 0 };
    return await response.json();
  } catch (error) {
    return { status: 'offline', database_connected: false, total_uploaded_datasets: 0 };
  }
}

/**
 * Fetches active MongoDB collections and document counts.
 */
export async function fetchCollections() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/collections`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) return { total_collections: 0, total_documents: 0, collections: [] };
    return await response.json();
  } catch (error) {
    return { total_collections: 0, total_documents: 0, collections: [] };
  }
}

/**
 * Fetches collections configured for admin cleaning with document counts.
 * Protected: Requires DATA_UPLOADER role.
 */
export async function fetchAdminCleanCollections() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/admin/clean/collections`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.detail || 'Failed to fetch collections');
    }
    return await response.json();
  } catch (error) {
    console.error('API fetchAdminCleanCollections error:', error);
    throw error;
  }
}

/**
 * Runs offline cleaning preview for an existing MongoDB collection (read-only).
 * Protected: Requires DATA_UPLOADER role.
 * @param {string} collection
 * @param {string[]} [ignoreFields]
 */
export async function previewAdminCleanCollection(collection, ignoreFields = null) {
  try {
    const payload = { collection };
    if (ignoreFields && ignoreFields.length) {
      payload.ignore_fields = ignoreFields;
    }
    const response = await fetch(`${API_BASE_URL}/api/admin/clean/preview`, {
      method: 'POST',
      headers: getAuthHeaders({
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.detail || 'Failed to preview collection cleaning');
    }
    return await response.json();
  } catch (error) {
    console.error('API previewAdminCleanCollection error:', error);
    throw error;
  }
}

/**
 * Fetches paginated changes for an active admin cleaning preview.
 * @param {string} previewId
 * @param {number} [offset=0]
 * @param {number} [limit=100]
 * @param {string} [action='']
 */
export async function fetchAdminCleanChanges(previewId, offset = 0, limit = 100, action = '') {
  try {
    const params = new URLSearchParams({
      offset: String(offset),
      limit: String(limit),
    });
    if (action && action !== 'all') {
      params.append('action', action);
    }
    const response = await fetch(`${API_BASE_URL}/api/admin/clean/preview/${previewId}/changes?${params.toString()}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.detail || 'Failed to fetch changes');
    }
    return await response.json();
  } catch (error) {
    console.error('API fetchAdminCleanChanges error:', error);
    throw error;
  }
}

/**
 * Downloads Excel audit report for an active admin cleaning preview.
 * @param {string} previewId
 * @param {string} collection
 */
export async function downloadAdminCleanReportExcel(previewId, collection = 'collection') {
  try {
    const response = await fetch(`${API_BASE_URL}/api/admin/clean/preview/${previewId}/report.xlsx`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.detail || 'Failed to download Excel report');
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${collection}_cleaning_report.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('API downloadAdminCleanReportExcel error:', error);
    throw error;
  }
}

/**
 * Applies the cleaning to MongoDB in 'new_collection' or 'replace' mode.
 * Protected: Requires DATA_UPLOADER role.
 * @param {string} previewId
 * @param {'new_collection'|'replace'} mode
 * @param {string|null} [confirmName]
 */
export async function applyAdminClean(previewId, mode, confirmName = null) {
  try {
    const payload = { preview_id: previewId, mode };
    if (confirmName) {
      payload.confirm_name = confirmName;
    }
    const response = await fetch(`${API_BASE_URL}/api/admin/clean/apply`, {
      method: 'POST',
      headers: getAuthHeaders({
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.detail || 'Failed to apply cleaning');
    }
    return await response.json();
  } catch (error) {
    console.error('API applyAdminClean error:', error);
    throw error;
  }
}

/**
 * Checks if any configured MongoDB collection lacks norm_company (uncleaned).
 * @returns {Promise<{has_uncleaned: boolean, uncleaned_collections?: string[], message?: string}>}
 */
export async function fetchAdminCleanStatus() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/admin/clean/status`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) return { has_uncleaned: false };
    return await response.json();
  } catch (error) {
    return { has_uncleaned: false };
  }
}


