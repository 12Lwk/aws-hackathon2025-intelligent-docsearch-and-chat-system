/**
 * Home Page JavaScript - Recent Views Management
 * Handles loading, displaying, and managing recent document views
 */

class RecentViewsManager {
    constructor() {
        this.loadingElement = document.getElementById('recent-views-loading');
        this.listElement = document.getElementById('recent-views-list');
        this.noViewsElement = document.getElementById('no-recent-views');
        this.clearButton = document.getElementById('clear-recent-views');
        
        this.init();
    }
    
    init() {
        // Load recent views on page load
        this.loadRecentViews();
        
        // Set up event listeners
        if (this.clearButton) {
            this.clearButton.addEventListener('click', () => this.clearRecentViews());
        }
    }
    
    showLoading() {
        if (this.loadingElement) this.loadingElement.style.display = 'block';
        if (this.listElement) this.listElement.style.display = 'none';
        if (this.noViewsElement) this.noViewsElement.style.display = 'none';
    }
    
    hideLoading() {
        if (this.loadingElement) this.loadingElement.style.display = 'none';
    }
    
    showNoViews() {
        if (this.noViewsElement) this.noViewsElement.style.display = 'block';
        if (this.listElement) this.listElement.style.display = 'none';
    }
    
    showViews() {
        if (this.listElement) this.listElement.style.display = 'block';
        if (this.noViewsElement) this.noViewsElement.style.display = 'none';
    }
    
    async loadRecentViews() {
        try {
            this.showLoading();
            
            const response = await fetch('/api/recent-views/?limit=5&user_session_only=true');
            const data = await response.json();
            
            this.hideLoading();
            
            if (data.status === 'success' && data.recent_views && data.recent_views.length > 0) {
                this.displayRecentViews(data.recent_views);
                this.showViews();
            } else {
                this.showNoViews();
            }
            
        } catch (error) {
            console.error('Error loading recent views:', error);
            this.hideLoading();
            this.showNoViews();
        }
    }
    
    displayRecentViews(recentViews) {
        if (!this.listElement) return;
        
        this.listElement.innerHTML = '';
        
        recentViews.forEach(view => {
            const viewElement = this.createViewElement(view);
            this.listElement.appendChild(viewElement);
        });
    }
    
    createViewElement(view) {
        const viewDiv = document.createElement('div');
        viewDiv.className = 'document-item';
        viewDiv.setAttribute('data-document-id', view.document_id);
        viewDiv.setAttribute('data-view-id', view.id);
        
        viewDiv.innerHTML = `
            <div class="document-info">
                <i class="${view.file_icon}"></i>
                <div class="document-details">
                    <p class="document-title">${this.escapeHtml(view.document_title)}</p>
                    <span class="document-time">Viewed ${view.time_ago} ago</span>
                </div>
            </div>
            <div class="document-actions">
                <button class="btn-action download-btn" title="Download document">
                    <i class="fas fa-download"></i>
                </button>
                <button class="btn-action close-btn" title="Remove from recent views">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        
        // Add click handlers
        const downloadButton = viewDiv.querySelector('.download-btn');
        const closeButton = viewDiv.querySelector('.close-btn');
        
        if (downloadButton) {
            downloadButton.addEventListener('click', (e) => {
                e.stopPropagation();
                this.downloadDocument(view.document_id, view.document_title);
            });
        }
        
        if (closeButton) {
            closeButton.addEventListener('click', (e) => {
                e.stopPropagation();
                this.removeFromRecentViews(view.id, viewDiv);
            });
        }
        
        return viewDiv;
    }
    
    formatCategory(category) {
        return category.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
    
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    async downloadDocument(documentId, documentTitle) {
        try {
            // Show loading state on download button
            const downloadBtn = document.querySelector(`[data-document-id="${documentId}"] .download-btn`);
            if (downloadBtn) {
                downloadBtn.disabled = true;
                downloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                downloadBtn.classList.add('loading');
            }
            
            const response = await fetch(`/api/documents/download/?id=${encodeURIComponent(documentId)}`);
            const data = await response.json();
            
            if (response.ok && data.download_url) {
                // Open download in new tab
                window.open(data.download_url, '_blank');
                
                this.showNotification(`Opening download: ${documentTitle}`, 'success');
                
                // Refresh recent views to show the new download activity
                setTimeout(() => {
                    this.loadRecentViews();
                }, 1000);
                
            } else {
                throw new Error(data.error || 'Download failed');
            }
            
        } catch (error) {
            console.error('Error downloading document:', error);
            this.showNotification(`Failed to download: ${documentTitle}`, 'error');
        } finally {
            // Reset download button
            const downloadBtn = document.querySelector(`[data-document-id="${documentId}"] .download-btn`);
            if (downloadBtn) {
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = '<i class="fas fa-download"></i>';
                downloadBtn.classList.remove('loading');
            }
        }
    }
    
    
    async removeFromRecentViews(viewId, viewElement) {
        try {
            // Animate removal
            viewElement.style.opacity = '0.5';
            viewElement.style.transform = 'translateX(100%)';
            
            // Remove from DOM after animation
            setTimeout(() => {
                if (viewElement.parentNode) {
                    viewElement.parentNode.removeChild(viewElement);
                    
                    // Check if list is empty
                    if (this.listElement.children.length === 0) {
                        this.showNoViews();
                    }
                }
            }, 300);
            
            this.showNotification('Removed from recent views', 'success');
            
        } catch (error) {
            console.error('Error removing from recent views:', error);
            this.showNotification('Failed to remove item', 'error');
            // Reset element if error
            viewElement.style.opacity = '1';
            viewElement.style.transform = 'translateX(0)';
        }
    }
    
    async viewDocument(documentId, documentTitle) {
        try {
            // Open the document in the chatbot interface with context
            const chatbotUrl = `/chatbot/?doc_id=${encodeURIComponent(documentId)}&doc_title=${encodeURIComponent(documentTitle)}`;
            window.open(chatbotUrl, '_blank');
            
        } catch (error) {
            console.error('Error opening document:', error);
            alert('Error opening document. Please try again.');
        }
    }
    
    async refreshRecentViews() {
        if (this.refreshButton) {
            const icon = this.refreshButton.querySelector('i');
            if (icon) {
                icon.classList.add('fa-spin');
            }
            this.refreshButton.disabled = true;
        }
        
        try {
            await this.loadRecentViews();
        } finally {
            if (this.refreshButton) {
                const icon = this.refreshButton.querySelector('i');
                if (icon) {
                    icon.classList.remove('fa-spin');
                }
                this.refreshButton.disabled = false;
            }
        }
    }
    
    async clearRecentViews() {
        if (!confirm('Are you sure you want to clear all recent views?')) {
            return;
        }
        
        try {
            if (this.clearButton) {
                this.clearButton.disabled = true;
            }
            
            const response = await fetch('/api/recent-views/clear/?user_session_only=true', {
                method: 'DELETE'
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showNoViews();
                this.showNotification('Recent views cleared successfully', 'success');
            } else {
                throw new Error(data.error || 'Failed to clear recent views');
            }
            
        } catch (error) {
            console.error('Error clearing recent views:', error);
            this.showNotification('Error clearing recent views', 'error');
        } finally {
            if (this.clearButton) {
                this.clearButton.disabled = false;
            }
        }
    }
    
    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
            <span>${message}</span>
        `;
        
        // Add to page
        document.body.appendChild(notification);
        
        // Show notification
        setTimeout(() => {
            notification.classList.add('show');
        }, 100);
        
        // Remove notification after 3 seconds
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new RecentViewsManager();
});