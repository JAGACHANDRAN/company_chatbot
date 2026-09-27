/**
 * API client layer for Calispec AI Search & Private Dataset Management
 */
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

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
      headers: {
        'Content-Type': 'application/json',
      },
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
    const response = await fetch(`${API_BASE_URL}/api/search?${params.toString()}`);
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
 * Fetches list of all uploaded datasets from MongoDB.
 */
export async function fetchDatasets() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/datasets`);
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
    const response = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}`);
    if (!response.ok) return null;
    return await response.json();
  } catch (error) {
    console.error('API fetchDatasetDetails error:', error);
    return null;
  }
}

/**
 * Deletes an uploaded dataset and its records from MongoDB.
 * @param {string} datasetId 
 */
export async function deleteDatasetApi(datasetId) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}`, {
      method: 'DELETE',
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
    const response = await fetch(`${API_BASE_URL}/api/collections`);
    if (!response.ok) return { total_collections: 0, total_documents: 0, collections: [] };
    return await response.json();
  } catch (error) {
    return { total_collections: 0, total_documents: 0, collections: [] };
  }
}
