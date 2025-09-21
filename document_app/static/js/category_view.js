// Category View JavaScript
let allDocuments = [];
let filteredDocuments = [];
let currentSort = 'upload_date_desc';
let currentView = 'grid';

document.addEventListener('DOMContentLoaded', function() {
    console.log('Category view loaded for:', window.categoryData);
    
    // Initialize the page
    initializePage();
    
    // Load documents
    loadDocuments();
    
    // Set up event listeners
    setupEventListeners();
});

function initializePage() {
    // Set initial view
    switchView('grid');
    
    // Update last updated time
    updateLastUpdatedTime();
}

function setupEventListeners() {
    // Search input
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(filterDocuments, 300));
    }
    
    // Sort select
    const sortSelect = document.getElementById('sort-select');
    if (sortSelect) {
        sortSelect.addEventListener('change', sortDocuments);
    }
}

async function loadDocuments() {
    try {
        showLoadingState();
        
        // TEMPORARY: Use simple test endpoint to verify frontend works
        const url = `/api/simple-test/`;
        console.log('Loading documents from:', url);
        
        const response = await fetch(url);
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('Raw response data:', JSON.stringify(data, null, 2));
        console.log('Response status field:', data.status);
        console.log('Response status type:', typeof data.status);
        console.log('Response documents:', data.documents);
        console.log('Response count:', data.count);
        
        if (data.status === 'success') {
            allDocuments = data.documents || [];
            filteredDocuments = [...allDocuments];
            
            console.log('Loaded documents:', allDocuments.length);
            console.log('First document:', allDocuments[0]);
            
            updateDocumentCount(allDocuments.length);
            updateLastUpdatedTime();
            
            if (allDocuments.length === 0) {
                console.log('No documents found, showing empty state');
                showEmptyState();
            } else {
                console.log('Documents found, hiding loading state');
                hideLoadingState();
                sortDocuments();
            }
        } else {
            console.error('API returned error status:', data);
            throw new Error(data.error || `API returned status: ${data.status}`);
        }
        
    } catch (error) {
        console.error('Error loading documents:', error);
        hideLoadingState();
        showEmptyState(); // Show empty state instead of staying in loading
        showToast('error', 'Failed to load documents: ' + error.message, 'fas fa-exclamation-triangle');
    }
}

function sortDocuments() {
    const sortSelect = document.getElementById('sort-select');
    currentSort = sortSelect.value;
    
    filteredDocuments.sort((a, b) => {
        switch (currentSort) {
            case 'upload_date_desc':
                return new Date(b.upload_date) - new Date(a.upload_date);
            case 'upload_date_asc':
                return new Date(a.upload_date) - new Date(b.upload_date);
            case 'filename_asc':
                return a.title.localeCompare(b.title);
            case 'filename_desc':
                return b.title.localeCompare(a.title);
            case 'file_size_desc':
                return (b.file_size || 0) - (a.file_size || 0);
            case 'file_size_asc':
                return (a.file_size || 0) - (b.file_size || 0);
            default:
                return 0;
        }
    });
    
    renderDocuments();
}

function filterDocuments() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase().trim();
    
    if (searchTerm === '') {
        filteredDocuments = [...allDocuments];
    } else {
        filteredDocuments = allDocuments.filter(doc => {
            return doc.title.toLowerCase().includes(searchTerm) ||
                   doc.content_summary.toLowerCase().includes(searchTerm) ||
                   doc.keywords.some(keyword => keyword.toLowerCase().includes(searchTerm));
        });
    }
    
    updateDocumentCount(filteredDocuments.length);
    sortDocuments();
}

function switchView(viewType) {
    currentView = viewType;
    
    // Update button states
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-view="${viewType}"]`).classList.add('active');
    
    // Update container class
    const container = document.getElementById('documents-container');
    container.className = `documents-container ${viewType}-view`;
    
    // Re-render documents with new view
    renderDocuments();
}

function renderDocuments() {
    const container = document.getElementById('documents-container');
    
    if (filteredDocuments.length === 0) {
        container.innerHTML = '<div class="no-results"><i class="fas fa-search"></i><p>No documents match your search criteria.</p></div>';
        return;
    }
    
    container.innerHTML = filteredDocuments.map(doc => createDocumentCard(doc)).join('');
}

function createDocumentCard(doc) {
    const uploadDate = new Date(doc.upload_date).toLocaleDateString();
    const timeAgo = getTimeAgo(doc.upload_date);
    
    return `
        <div class="document-card" onclick="openDocumentModal('${doc.id}')">
            <div class="document-header">
                <i class="${doc.file_icon || 'fas fa-file'} document-icon"></i>
                <div class="document-actions" onclick="event.stopPropagation()">
                    <button class="action-btn download" onclick="downloadDocument('${doc.id}')" title="Download">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="action-btn delete" onclick="deleteDocument('${doc.id}')" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
            <div class="document-body">
                <h3 class="document-title" title="${doc.title}">${truncateText(doc.title || 'Unknown Document', 50)}</h3>
                <div class="document-meta">
                    <span><i class="fas fa-calendar"></i> ${uploadDate}</span>
                    <span><i class="fas fa-clock"></i> ${timeAgo}</span>
                </div>
            </div>
        </div>
    `;
}

function openDocumentModal(documentId) {
    const doc = allDocuments.find(d => d.id === documentId);
    if (!doc) return;
    
    const modal = document.getElementById('document-modal');
    const modalTitle = document.getElementById('modal-title');
    const documentPreview = document.getElementById('document-preview');
    
    modalTitle.textContent = doc.title;
    
    documentPreview.innerHTML = `
        <div class="document-info">
            <div class="document-icon-large">
                <i class="${doc.file_icon}"></i>
            </div>
            <div class="document-details">
                <h4>${doc.title}</h4>
                <div class="document-meta-detailed">
                    <p><strong>Category:</strong> ${window.categoryData.name}</p>
                    <p><strong>Upload Date:</strong> ${new Date(doc.upload_date).toLocaleString()}</p>
                    <p><strong>File Size:</strong> ${formatFileSize(doc.file_size)}</p>
                    <p><strong>File Type:</strong> ${doc.file_type}</p>
                    ${doc.confidence_score ? `<p><strong>AI Confidence:</strong> ${Math.round(doc.confidence_score * 100)}%</p>` : ''}
                </div>
                ${doc.content_summary ? `
                    <div class="content-preview">
                        <h5>Content Summary:</h5>
                        <p>${doc.content_summary}</p>
                    </div>
                ` : ''}
                ${doc.keywords && doc.keywords.length > 0 ? `
                    <div class="keywords-section">
                        <h5>Keywords:</h5>
                        <div class="keywords-list">
                            ${doc.keywords.map(keyword => `<span class="keyword-tag">${keyword}</span>`).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>
        </div>
    `;
    
    // Set up action buttons
    document.getElementById('download-btn').onclick = () => downloadDocument(doc.id);
    document.getElementById('view-in-chat-btn').onclick = () => openInChat(doc.id);
    document.getElementById('delete-btn').onclick = () => deleteDocument(doc.id);
    
    modal.classList.add('show');
}

function closeModal() {
    const modal = document.getElementById('document-modal');
    modal.classList.remove('show');
}

async function downloadDocument(documentId) {
    try {
        showToast('info', 'Starting download...', 'fas fa-download');
        
        const response = await fetch(`/api/documents/download/?id=${documentId}`);
        const data = await response.json();
        
        if (response.ok && data.download_url) {
            window.open(data.download_url, '_blank');
            showToast('success', 'Download started', 'fas fa-check-circle');
        } else {
            showToast('error', 'Download failed', 'fas fa-exclamation-triangle');
        }
    } catch (error) {
        console.error('Download error:', error);
        showToast('error', 'Download failed', 'fas fa-exclamation-triangle');
    }
}

function openInChat(documentId) {
    // Open document in chatbot
    window.open(`/chatbot/?doc=${documentId}`, '_blank');
    closeModal();
}

async function deleteDocument(documentId) {
    if (!confirm('Are you sure you want to delete this document? This action cannot be undone.')) {
        return;
    }
    
    try {
        const response = await fetch('/api/documents/delete/', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ document_id: documentId })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Remove document from arrays
            allDocuments = allDocuments.filter(doc => doc.id !== documentId);
            filteredDocuments = filteredDocuments.filter(doc => doc.id !== documentId);
            
            // Update UI
            updateDocumentCount(allDocuments.length);
            renderDocuments();
            closeModal();
            
            showToast('success', 'Document deleted successfully', 'fas fa-check-circle');
        } else {
            showToast('error', 'Failed to delete document', 'fas fa-exclamation-triangle');
        }
    } catch (error) {
        console.error('Delete error:', error);
        showToast('error', 'Failed to delete document', 'fas fa-exclamation-triangle');
    }
}

async function testAPI() {
    try {
        showToast('info', 'Testing API...', 'fas fa-bug');
        
        const response = await fetch(`/api/test-category/?category=${window.categoryData.category}`);
        const data = await response.json();
        
        console.log('API Test Result:', data);
        
        if (data.status === 'success') {
            const accessible = data.dynamodb_accessible ? 'accessible' : 'not accessible';
            showToast('success', `API working! Found ${data.dynamodb_docs_found} docs in DynamoDB (${accessible})`, 'fas fa-check-circle');
        } else {
            showToast('error', `API Error: ${data.error}`, 'fas fa-exclamation-triangle');
        }
        
    } catch (error) {
        console.error('API Test Failed:', error);
        showToast('error', 'API test failed: ' + error.message, 'fas fa-times-circle');
    }
}

async function refreshDocuments() {
    const refreshBtn = document.querySelector('.category-actions .btn-secondary:nth-child(2)'); // Second button
    const icon = refreshBtn.querySelector('i');
    
    // Add spinning animation
    icon.classList.add('fa-spin');
    refreshBtn.disabled = true;
    
    showToast('info', 'Refreshing documents...', 'fas fa-sync-alt');
    
    try {
        await loadDocuments();
        showToast('success', 'Documents refreshed!', 'fas fa-check-circle');
    } catch (error) {
        showToast('error', 'Failed to refresh documents', 'fas fa-exclamation-triangle');
    } finally {
        icon.classList.remove('fa-spin');
        refreshBtn.disabled = false;
    }
}

// Utility Functions
function updateDocumentCount(count) {
    const totalDocuments = document.getElementById('total-documents');
    if (totalDocuments) {
        totalDocuments.textContent = count;
    }
}

function updateLastUpdatedTime() {
    const lastUpdated = document.getElementById('last-updated');
    if (lastUpdated) {
        lastUpdated.textContent = new Date().toLocaleString();
    }
}

function showLoadingState() {
    document.getElementById('loading-state').style.display = 'flex';
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('documents-container').style.display = 'none';
}

function hideLoadingState() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('documents-container').style.display = 'grid';
}

function showEmptyState() {
    document.getElementById('loading-state').style.display = 'none';
    document.getElementById('empty-state').style.display = 'flex';
    document.getElementById('documents-container').style.display = 'none';
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function truncateText(text, maxLength) {
    if (!text || text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

function getTimeAgo(dateString) {
    const now = new Date();
    const date = new Date(dateString);
    const diffInSeconds = Math.floor((now - date) / 1000);
    
    if (diffInSeconds < 60) return 'Just now';
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} minutes ago`;
    if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} hours ago`;
    if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)} days ago`;
    return date.toLocaleDateString();
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Toast notification system
function showToast(type, message, iconClass) {
    const toast = document.getElementById('toast');
    const toastIcon = toast.querySelector('.toast-icon');
    const toastMessage = toast.querySelector('.toast-message');
    
    // Set content
    toastIcon.className = `toast-icon ${iconClass}`;
    toastMessage.textContent = message;
    
    // Set type
    toast.className = `toast ${type} show`;
    
    // Auto hide after 4 seconds
    setTimeout(() => {
        hideToast();
    }, 4000);
}

function hideToast() {
    const toast = document.getElementById('toast');
    toast.classList.remove('show');
}

// Close modal when clicking outside
document.addEventListener('click', function(event) {
    const modal = document.getElementById('document-modal');
    if (event.target === modal) {
        closeModal();
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        closeModal();
    }
});
