document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search-input');
    const searchButton = document.getElementById('search-button');
    const searchResultsContainer = document.getElementById('search-results');
    const loadingIndicator = document.getElementById('loading-indicator');
    const suggestionChips = document.querySelectorAll('.suggestion-chip');

    const performSearch = async (query) => {
        if (!query.trim()) return;

        loadingIndicator.classList.remove('hidden');
        searchResultsContainer.innerHTML = '';

        try {
            const response = await fetch('/api/ai-search/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ 
                    query: query.trim(),
                    min_similarity: 0.6,
                    max_results: 5
                })
            });

            const data = await response.json();
            displayResults(data, query);

        } catch (error) {
            searchResultsContainer.innerHTML = `<div class="error-message">Search failed: ${error.message}</div>`;
        } finally {
            loadingIndicator.classList.add('hidden');
        }
    };

    const displayResults = (data, query) => {
        if (!data.results || data.results.length === 0) {
            searchResultsContainer.innerHTML = `
                <div class="no-results">
                    <h3>No documents found</h3>
                    <p>No documents found with 60% similarity or higher for "${query}"</p>
                </div>
            `;
            return;
        }

        let resultsHtml = '';
        
        data.results.forEach((result) => {
            const relevance = result.similarity_percentage || Math.round(result.relevance_score * 100);
            const categoryDisplay = (result.category && result.category !== 'Unknown') 
                ? `<span class="file-category">${result.category.replace('_', ' ')}</span>` 
                : '';
            
            resultsHtml += `
                <div class="result-card">
                    <div class="result-header">
                        ${categoryDisplay}
                        <div class="relevance-score">Similarity: ${relevance}%</div>
                    </div>
                    <h3 class="document-title">
                        ${result.title}
                    </h3>
                    <p class="excerpt">${result.excerpt || 'No preview available'}</p>
                    <div class="result-actions">
                        <button onclick="downloadDocument('${result.id}', '${result.title.replace(/'/g, '&apos;')}')" class="btn-download">
                            <i class="fas fa-download"></i> Download
                        </button>
                    </div>
                </div>
            `;
        });
        
        searchResultsContainer.innerHTML = resultsHtml;
    };

    window.viewDocument = async (docId, title) => {
        try {
            const response = await fetch(`/api/documents/view/?id=${encodeURIComponent(docId)}`);
            const data = await response.json();
            
            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }
            
            // Open document content in new window or modal
            const newWindow = window.open('', '_blank');
            newWindow.document.write(`
                <html>
                    <head><title>${title}</title></head>
                    <body>
                        <h1>${title}</h1>
                        <p><strong>Category:</strong> ${data.category}</p>
                        <hr>
                        <div>${data.content}</div>
                    </body>
                </html>
            `);
        } catch (error) {
            console.error('View error:', error);
        }
    };

    window.downloadDocument = async (docId, title) => {
        try {
            const response = await fetch(`/api/documents/download/?id=${encodeURIComponent(docId)}`);
            const data = await response.json();
            
            if (data.download_url) {
                if (data.is_text_only) {
                    const link = document.createElement('a');
                    link.href = data.download_url;
                    link.download = data.filename;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                } else {
                    window.open(data.download_url, '_blank');
                }
            }
        } catch (error) {
            console.error('Download error:', error);
        }
    };

    searchButton.addEventListener('click', () => {
        performSearch(searchInput.value.trim());
    });

    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            performSearch(searchInput.value.trim());
        }
    });

    suggestionChips.forEach(chip => {
        chip.addEventListener('click', (e) => {
            e.preventDefault();
            const query = chip.innerText.replace(/"/g, '');
            searchInput.value = query;
            performSearch(query);
        });
    });

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
});