document.addEventListener('DOMContentLoaded', function() {
    const themeButtons = document.querySelectorAll('.theme-btn');

    themeButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            e.preventDefault();
            themeButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            // Here you would add the logic to change the theme
            console.log('Theme changed to:', button.dataset.theme);
        });
    });
});