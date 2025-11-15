document.addEventListener('DOMContentLoaded', function() {
    // 1. Анимация кнопки "В корзину"
    document.querySelectorAll('.add-to-cart-form').forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();

            const button = this.querySelector('button[type="submit"]');
            const originalText = button.innerHTML;

            // Замена текста и стиля
            button.innerHTML = '✅ Добавлено!';
            button.classList.remove('btn-outline-primary');
            button.classList.add('btn-success');
            button.disabled = true;

            // Отправка формы
            this.submit();

            // Возвращение к оригинальному виду через 1.5 секунды
            setTimeout(() => {
                button.innerHTML = originalText;
                button.classList.remove('btn-success');
                button.classList.add('btn-outline-primary');
                button.disabled = false;
            }, 1500);
        });
    });

    // 2. Плавное появление карточек меню
    const menuCards = document.querySelectorAll('.card');

    menuCards.forEach((card, index) => {
        card.style.opacity = 0;
        card.style.transform = 'translateY(20px)';

        setTimeout(() => {
            card.style.transition = 'opacity 0.6s ease-out, transform 0.6s ease-out';
            card.style.opacity = 1;
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
});
