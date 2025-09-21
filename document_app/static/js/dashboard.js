document.addEventListener('DOMContentLoaded', function() {
    // Doughnut Chart for Document Types
    const docTypeCtx = document.getElementById('docTypeChart').getContext('2d');
    new Chart(docTypeCtx, {
        type: 'doughnut',
        data: {
            labels: ['PDF', 'DOCX', 'PNG', 'JPG'],
            datasets: [{
                data: [300, 150, 80, 120],
                backgroundColor: ['#0A7CFF', '#4CAF50', '#FFC107', '#F44336'],
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom',
                },
                title: {
                    display: false
                }
            }
        }
    });

    // Line Chart for Upload Frequency
    const uploadFrequencyCtx = document.getElementById('uploadFrequencyChart').getContext('2d');
    new Chart(uploadFrequencyCtx, {
        type: 'line',
        data: {
            labels: ['January', 'February', 'March', 'April', 'May', 'June'],
            datasets: [{
                label: 'Documents Uploaded',
                data: [65, 59, 80, 81, 56, 55],
                fill: false,
                borderColor: '#0A7CFF',
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
});