document.addEventListener('DOMContentLoaded', function() {
    const uploadZone = document.getElementById('upload-zone');
    const browseBtn = document.getElementById('browse-btn');
    const fileInput = document.getElementById('file-input');
    const uploadProgressSection = document.getElementById('upload-progress-section');
    const uploadedFilesSection = document.getElementById('uploaded-files-section');
    const filesTableBody = document.getElementById('files-table-body');
    const fileCountSpan = document.getElementById('file-count');
    const progressFill = document.getElementById('overall-progress');
    const progressText = document.getElementById('progress-text');
    
    let uploadedFiles = [];

    // Upload zone click handler
    uploadZone.addEventListener('click', () => {
        fileInput.click();
    });
    
    // Browse button click handler
    browseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFiles(fileInput.files);
        }
    });

    // Enhanced drag and drop
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFiles(e.dataTransfer.files);
        }
    });

    async function handleFiles(files) {
        const validFiles = validateFiles(Array.from(files));
        if (validFiles.length === 0) return;
        
        showToast('info', `Uploading ${validFiles.length} files...`, 'fas fa-upload');
        
        // Show progress section
        uploadProgressSection.style.display = 'block';
        
        try {
            // Real upload to AWS pipeline
            const formData = new FormData();
            validFiles.forEach(file => formData.append('files', file));
            
            const response = await fetch('/api/upload-files/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                // Add files to table with processing status
                addFilesToTable(result.documents);
                showToast('success', result.message, 'fas fa-check-circle');
                
                // Start polling for status updates
                result.documents.forEach(doc => {
                    pollDocumentStatus(doc.id);
                });
                
                // Refresh folder structure after upload
                setTimeout(() => {
                    loadFolderStructure();
                    showToast('info', 'Documents are being classified...', 'fas fa-brain');
                }, 2000); // Wait 2 seconds for processing to start
                
                // Set up periodic refresh for classification updates
                const refreshInterval = setInterval(() => {
                    loadFolderStructure();
                }, 10000); // Refresh every 10 seconds
                
                // Stop refreshing after 2 minutes (classification should be done)
                setTimeout(() => {
                    clearInterval(refreshInterval);
                    loadFolderStructure(); // Final refresh
                    showToast('success', 'Document classification complete!', 'fas fa-check-circle');
                }, 120000); // 2 minutes
                
            } else {
                showToast('error', result.error || 'Upload failed', 'fas fa-times-circle');
            }
        } catch (error) {
            showToast('error', 'Upload failed: ' + error.message, 'fas fa-times-circle');
        } finally {
            uploadProgressSection.style.display = 'none';
        }
    }
    
    function validateFiles(files) {
        const validTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
        const maxSize = 10 * 1024 * 1024; // 10MB
        const maxFiles = 25;
        
        if (files.length > maxFiles) {
            showToast('error', `Maximum ${maxFiles} files allowed`, 'fas fa-exclamation-triangle');
            return [];
        }
        
        const validFiles = files.filter(file => {
            if (!validTypes.includes(file.type) && !file.name.toLowerCase().match(/\.(pdf|png|jpg|jpeg|doc|docx)$/)) {
                showToast('error', `${file.name}: Invalid file type. Only PDF, PNG, JPG, DOC allowed.`, 'fas fa-times-circle');
                return false;
            }
            if (file.size > maxSize) {
                showToast('error', `${file.name}: File too large. Maximum 10MB allowed.`, 'fas fa-times-circle');
                return false;
            }
            return true;
        });
        
        return validFiles;
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
    
    function pollDocumentStatus(documentId) {
        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/document-status/${documentId}/`);
                const doc = await response.json();
                
                updateDocumentRow(doc);
                
                if (doc.status === 'completed' || doc.status === 'failed') {
                    clearInterval(pollInterval);
                }
            } catch (error) {
                console.error('Status polling error:', error);
                clearInterval(pollInterval);
            }
        }, 2000); // Poll every 2 seconds
    }
    
    function addFilesToTable(documents) {
        uploadedFilesSection.style.display = 'block';
        
        documents.forEach(doc => {
            const row = document.createElement('tr');
            row.setAttribute('data-doc-id', doc.id);
            
            const uploadTime = new Date().toLocaleString();
            const statusClass = getStatusClass(doc.status);
            
            row.innerHTML = `
                <td>
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <i class="fas fa-file-pdf"></i>
                        <span>${doc.name}</span>
                    </div>
                </td>
                <td>${uploadTime}</td>
                <td>-</td>
                <td><span class="status-badge ${statusClass}">${doc.status}</span></td>
                <td>
                    <button class="btn-icon" onclick="removeFile(this)" title="Remove file">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            `;
            
            filesTableBody.appendChild(row);
            uploadedFiles.push(doc);
        });
        
        updateFileCount();
    }
    
    function updateDocumentRow(doc) {
        const row = document.querySelector(`[data-doc-id="${doc.id}"]`);
        if (row) {
            const statusBadge = row.querySelector('.status-badge');
            statusBadge.textContent = doc.status;
            statusBadge.className = `status-badge ${getStatusClass(doc.status)}`;
            
            if (doc.category) {
                // Add category info if available
                const nameCell = row.querySelector('td:first-child span');
                nameCell.innerHTML = `${doc.name} <small>(${doc.category})</small>`;
            }
        }
    }
    
    function getStatusClass(status) {
        switch(status) {
            case 'uploaded': return 'status-uploading';
            case 'processing': return 'status-processing';
            case 'completed': return 'status-completed';
            case 'failed': return 'status-error';
            default: return 'status-uploading';
        }
    }
    
    function updateFileCount() {
        fileCountSpan.textContent = `${uploadedFiles.length} files`;
    }
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    function getFileIcon(fileType) {
        if (fileType === 'application/pdf') return 'pdf';
        if (fileType.startsWith('image/')) return 'image';
        if (fileType === 'application/msword' || fileType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') return 'word';
        return 'alt';
    }
    
    // Global function for removing files
    window.removeFile = function(button) {
        const row = button.closest('tr');
        const fileName = row.querySelector('td').textContent.trim();
        
        // Remove from uploaded files array
        uploadedFiles = uploadedFiles.filter(file => file.name !== fileName);
        
        // Remove row
        row.remove();
        
        // Update count
        updateFileCount();
        
        // Hide section if no files
        if (uploadedFiles.length === 0) {
            uploadedFilesSection.style.display = 'none';
        }
        
        showToast('info', `Removed ${fileName}`, 'fas fa-trash');
    };
    
    // Toast notification system
    window.showToast = function(type, message, iconClass) {
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
    };
    
    window.hideToast = function() {
        const toast = document.getElementById('toast');
        toast.classList.remove('show');
    };

    // Category Management Functions - removed toggleCategory since we don't need dropdown anymore

    // viewCategory function is defined globally outside DOMContentLoaded

    window.deleteCategory = function(categoryId) {
        if (confirm(`Are you sure you want to delete the ${categoryId} category?`)) {
            const card = document.querySelector(`[data-category="${categoryId}"]`);
            card.style.opacity = '0.5';
            showToast('info', `Deleting ${categoryId} category...`, 'fas fa-trash');
            
            // Simulate deletion
            setTimeout(() => {
                card.remove();
                showToast('success', `${categoryId} category deleted successfully`, 'fas fa-check-circle');
            }, 1000);
        }
    };

    // Test API function
    window.testAPI = async function() {
        console.log('Testing API...');
        try {
            const response = await fetch('/api/test/');
            const result = await response.json();
            alert('API Test: ' + result.message);
            console.log('API Response:', result);
        } catch (error) {
            alert('API Test Failed: ' + error.message);
            console.error('API Error:', error);
        }
    };

    // Add Category Button
    document.getElementById('add-category-btn')?.addEventListener('click', () => {
        const categoryName = prompt('Enter new category name:');
        if (categoryName && categoryName.trim()) {
            addNewCategory(categoryName.trim());
        }
    });

    function addNewCategory(name) {
        const grid = document.getElementById('categories-grid');
        const categoryId = name.toLowerCase().replace(/\s+/g, '-');
        
        const newCard = document.createElement('div');
        newCard.className = 'category-card';
        newCard.setAttribute('data-category', categoryId);
        
        newCard.innerHTML = `
            <div class="category-header" onclick="toggleCategory('${categoryId}')">
                <div class="category-info">
                    <i class="fas fa-folder category-icon"></i>
                    <div class="category-details">
                        <h3>${name}</h3>
                        <span class="file-count">0 files</span>
                    </div>
                </div>
                <div class="category-controls">
                    <i class="fas fa-chevron-down expand-icon"></i>
                </div>
            </div>
            <div class="category-content" id="${categoryId}-content">
                <div class="category-stats">
                    <div class="stat-item">
                        <i class="fas fa-file"></i>
                        <span>No files yet</span>
                    </div>
                </div>
                <div class="category-actions-expanded">
                    <button class="btn-secondary" onclick="viewCategory('${categoryId}')">
                        <i class="fas fa-eye"></i> View Files
                    </button>
                    <button class="btn-icon" onclick="deleteCategory('${categoryId}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        
        grid.appendChild(newCard);
        showToast('success', `Category "${name}" created successfully!`, 'fas fa-plus-circle');
    }

    // Load folder structure on page load
    loadFolderStructure();
});

// Folder View Management Functions
async function loadFolderStructure() {
    try {
        console.log('Loading folder structure...');
        
        const response = await fetch('/api/folder-structure/');
        const data = await response.json();
        
        if (data.status === 'success') {
            updateFolderDisplay(data.folder_structure);
        } else {
            console.error('Failed to load folder structure:', data.error);
        }
        
    } catch (error) {
        console.error('Error loading folder structure:', error);
    }
}

function updateFolderDisplay(folderStructure) {
    console.log('Updating folder display with:', folderStructure);
    
    Object.keys(folderStructure).forEach(categoryId => {
        const folder = folderStructure[categoryId];
        const categoryCard = document.querySelector(`[data-category="${categoryId}"]`);
        
        if (categoryCard) {
            // Update file count with animation
            const fileCountSpan = categoryCard.querySelector('.file-count');
            if (fileCountSpan) {
                const oldCount = parseInt(fileCountSpan.textContent) || 0;
                const newCount = folder.total_files;
                
                if (newCount !== oldCount) {
                    // Animate count change
                    fileCountSpan.style.transform = 'scale(1.2)';
                    fileCountSpan.style.color = '#007bff';
                    setTimeout(() => {
                        fileCountSpan.style.transform = 'scale(1)';
                        fileCountSpan.style.color = '';
                    }, 300);
                }
                
                fileCountSpan.textContent = `${newCount} files`;
            }
            
            // Update category icon color
            const categoryIcon = categoryCard.querySelector('.category-icon');
            if (categoryIcon && folder.color) {
                categoryIcon.style.color = folder.color;
            }
            
            // Update file type stats
            const categoryContent = categoryCard.querySelector('.category-content');
            if (categoryContent) {
                const statsContainer = categoryContent.querySelector('.category-stats');
                if (statsContainer) {
                    statsContainer.innerHTML = '';
                    
                    // Add file type statistics
                    Object.keys(folder.file_types).forEach(fileType => {
                        const count = folder.file_types[fileType];
                        if (count > 0) {
                            const statItem = document.createElement('div');
                            statItem.className = 'stat-item';
                            
                            let icon = 'fas fa-file';
                            let label = fileType.toUpperCase();
                            
                            switch(fileType) {
                                case 'pdf':
                                    icon = 'fas fa-file-pdf';
                                    label = 'PDFs';
                                    break;
                                case 'doc':
                                    icon = 'fas fa-file-word';
                                    label = 'DOCs';
                                    break;
                                case 'image':
                                    icon = 'fas fa-file-image';
                                    label = 'Images';
                                    break;
                                default:
                                    label = 'Others';
                            }
                            
                            statItem.innerHTML = `
                                <i class="${icon}"></i>
                                <span>${count} ${label}</span>
                            `;
                            
                            statsContainer.appendChild(statItem);
                        }
                    });
                    
                    // If no files, show placeholder
                    if (folder.total_files === 0) {
                        statsContainer.innerHTML = `
                            <div class="stat-item">
                                <i class="fas fa-folder-open"></i>
                                <span>No files yet</span>
                            </div>
                        `;
                    }
                }
            }
        }
    });
}

// Make function globally accessible
window.viewCategory = async function(categoryId) {
    try {
        console.log(`Viewing category: ${categoryId}`);
        console.log('Event target:', event.target);
        console.log('Current URL:', window.location.href);
        
        // Show immediate feedback
        showToast('info', `Opening ${categoryId} category...`, 'fas fa-folder-open');
        
        // Navigate to dedicated category page
        const testUrl = `/category/${categoryId}/`;
        console.log('Navigating to:', testUrl);
        console.log('Full URL will be:', window.location.origin + testUrl);
        
        // Add a small delay to see the toast
        setTimeout(() => {
            window.location.href = testUrl;
        }, 500);
        
    } catch (error) {
        console.error('Error viewing category:', error);
        showToast('error', 'Error navigating to category: ' + error.message, 'fas fa-exclamation-triangle');
    }
}

// Test function to verify button clicks work
window.testViewCategory = function(categoryId) {
    alert(`Button clicked for category: ${categoryId}`);
    console.log(`Test function called with: ${categoryId}`);
}

// Debug function to test URL patterns
window.testURL = function(categoryId) {
    const testUrl = `/category/${categoryId}/`;
    console.log('Testing URL:', testUrl);
    
    // Test if URL is accessible
    fetch(testUrl, { method: 'HEAD' })
        .then(response => {
            console.log('URL test response:', response.status);
            if (response.ok) {
                console.log('URL is accessible!');
                showToast('success', 'URL is working!', 'fas fa-check-circle');
            } else {
                console.log('URL returned error:', response.status);
                showToast('error', `URL returned ${response.status}`, 'fas fa-exclamation-triangle');
            }
        })
        .catch(error => {
            console.error('URL test failed:', error);
            showToast('error', 'URL test failed', 'fas fa-times-circle');
        });
}

function displayCategoryDocuments(categoryId, documents) {
    // Create modal for displaying documents
    const modal = document.createElement('div');
    modal.className = 'documents-modal';
    modal.innerHTML = `
        <div class="modal-content large">
            <div class="modal-header">
                <h2><i class="fas fa-folder-open"></i> ${getCategoryDisplayName(categoryId)}</h2>
                <button class="close-modal" onclick="closeDocumentsModal()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal-body">
                <div class="documents-grid" id="documents-grid">
                    ${documents.length === 0 ? 
                        '<div class="no-documents"><i class="fas fa-folder-open"></i><p>No documents in this category</p></div>' :
                        documents.map(doc => createDocumentCard(doc)).join('')
                    }
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Show modal with animation
    setTimeout(() => {
        modal.classList.add('show');
    }, 10);
}

function createDocumentCard(doc) {
    const uploadDate = new Date(doc.upload_date).toLocaleDateString();
    const fileSize = formatFileSize(doc.file_size);
    
    return `
        <div class="document-card" data-document-id="${doc.id}">
            <div class="document-header">
                <i class="${doc.file_icon}"></i>
                <div class="document-actions">
                    <button class="btn-icon" onclick="downloadDocument('${doc.id}')" title="Download">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="btn-icon delete-btn" onclick="deleteDocument('${doc.id}')" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
            <div class="document-body">
                <h4 class="document-title" title="${doc.title}">${truncateText(doc.title, 30)}</h4>
                <div class="document-meta">
                    <span class="upload-date"><i class="fas fa-calendar"></i> ${uploadDate}</span>
                    <span class="file-size"><i class="fas fa-weight-hanging"></i> ${fileSize}</span>
                </div>
                <div class="document-summary">
                    ${doc.content_summary ? truncateText(doc.content_summary, 100) : 'No summary available'}
                </div>
                <div class="document-keywords">
                    ${doc.keywords.slice(0, 3).map(keyword => 
                        `<span class="keyword-tag">${keyword}</span>`
                    ).join('')}
                </div>
            </div>
        </div>
    `;
}

function getCategoryDisplayName(categoryId) {
    const categoryNames = {
        'policies_guidelines': 'Policies & Guidelines',
        'operations_production': 'Operations & Production',
        'maintenance_technical': 'Maintenance & Technical',
        'training_knowledge': 'Training & Knowledge',
        'others': 'Others'
    };
    return categoryNames[categoryId] || categoryId;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

async function downloadDocument(documentId) {
    try {
        const response = await fetch(`/api/documents/download/?id=${documentId}`);
        const data = await response.json();
        
        if (response.ok && data.download_url) {
            window.open(data.download_url, '_blank');
            showToast('success', 'Download started', 'fas fa-download');
        } else {
            showToast('error', 'Download failed', 'fas fa-exclamation-triangle');
        }
    } catch (error) {
        console.error('Download error:', error);
        showToast('error', 'Download failed', 'fas fa-exclamation-triangle');
    }
}

async function deleteDocument(documentId) {
    if (!confirm('Are you sure you want to delete this document?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/documents/delete/', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ document_id: documentId })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Remove document card from UI
            const documentCard = document.querySelector(`[data-document-id="${documentId}"]`);
            if (documentCard) {
                documentCard.remove();
            }
            
            showToast('success', 'Document deleted successfully', 'fas fa-trash');
            
            // Refresh folder structure
            loadFolderStructure();
        } else {
            showToast('error', 'Failed to delete document', 'fas fa-exclamation-triangle');
        }
    } catch (error) {
        console.error('Delete error:', error);
        showToast('error', 'Failed to delete document', 'fas fa-exclamation-triangle');
    }
}

function closeDocumentsModal() {
    const modal = document.querySelector('.documents-modal');
    if (modal) {
        modal.classList.remove('show');
        setTimeout(() => {
            modal.remove();
        }, 300);
    }
}

// Global function for refresh button
window.refreshFolders = function() {
    const refreshBtn = document.getElementById('refresh-folders-btn');
    const icon = refreshBtn.querySelector('i');
    
    // Add spinning animation
    icon.classList.add('fa-spin');
    refreshBtn.disabled = true;
    
    showToast('info', 'Refreshing folder structure...', 'fas fa-sync-alt');
    
    loadFolderStructure().then(() => {
        // Remove spinning animation
        icon.classList.remove('fa-spin');
        refreshBtn.disabled = false;
        showToast('success', 'Folders refreshed!', 'fas fa-check-circle');
    }).catch(() => {
        icon.classList.remove('fa-spin');
        refreshBtn.disabled = false;
        showToast('error', 'Failed to refresh folders', 'fas fa-exclamation-triangle');
    });
}