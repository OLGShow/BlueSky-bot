#!/bin/bash

# =================================================================
# BlueSky Bot Auto-Installer для Ubuntu Server 24.04.2
# Автоматическая установка и настройка бота одной командой
# =================================================================

set -e  # Останавливаем при любой ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для красивого вывода
print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}📋 $1${NC}"
}

# Проверка запуска от имени пользователя (НЕ root)
check_user() {
    if [ "$EUID" -eq 0 ]; then
        print_error "Не запускайте скрипт от имени root! Используйте обычного пользователя."
        echo "Выполните: curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/BlueSky-Bot/main/install.sh | bash"
        exit 1
    fi
}

# Проверка операционной системы
check_os() {
    print_header "Проверка операционной системы"
    
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [[ "$ID" == "ubuntu" && "$VERSION_ID" == "24.04" ]]; then
            print_success "Ubuntu 24.04 обнаружена"
        else
            print_warning "Обнаружена $PRETTY_NAME (рекомендуется Ubuntu 24.04)"
        fi
    else
        print_warning "Не удалось определить операционную систему"
    fi
}

# Установка системных зависимостей
install_system_deps() {
    print_header "Установка системных зависимостей"
    
    # Обновляем пакеты
    print_info "Обновление списка пакетов..."
    sudo apt update
    
    # Устанавливаем необходимые пакеты
    print_info "Установка системных пакетов..."
    sudo apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        git \
        curl \
        build-essential \
        libssl-dev \
        libffi-dev \
        software-properties-common \
        tmux \
        htop \
        nano
    
    print_success "Системные зависимости установлены"
}

# Клонирование репозитория
clone_repository() {
    print_header "Клонирование репозитория"
    
    BOT_DIR="$HOME/BlueSky-Bot"
    
    if [ -d "$BOT_DIR" ]; then
        print_warning "Директория $BOT_DIR уже существует"
        read -p "Удалить существующую установку и начать заново? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$BOT_DIR"
            print_info "Старая установка удалена"
        else
            print_error "Установка отменена"
            exit 1
        fi
    fi
    
    # Здесь замените YOUR_USERNAME на ваш GitHub username
    REPO_URL="https://github.com/YOUR_USERNAME/BlueSky-Bot.git"
    
    print_info "Клонирование из $REPO_URL..."
    git clone "$REPO_URL" "$BOT_DIR"
    cd "$BOT_DIR"
    
    print_success "Репозиторий клонирован в $BOT_DIR"
}

# Создание виртуального окружения Python
setup_python_env() {
    print_header "Настройка Python окружения"
    
    cd "$HOME/BlueSky-Bot"
    
    # Создаем виртуальное окружение
    print_info "Создание виртуального окружения..."
    python3 -m venv venv
    
    # Активируем окружение
    source venv/bin/activate
    
    # Обновляем pip
    print_info "Обновление pip..."
    pip install --upgrade pip setuptools wheel
    
    # Устанавливаем зависимости
    print_info "Установка Python зависимостей..."
    pip install -r requirements.txt
    
    print_success "Python окружение настроено"
}

# Настройка конфигурации
setup_configuration() {
    print_header "Настройка конфигурации"
    
    cd "$HOME/BlueSky-Bot"
    
    # Создаем файл с переменными окружения
    if [ ! -f ".env" ]; then
        print_info "Создание файла конфигурации..."
        cat > .env << EOF
# BlueSky Bot Configuration
# =========================

# ОБЯЗАТЕЛЬНЫЕ НАСТРОЙКИ
BLUESKY_HANDLE=your-bot.bsky.social
BLUESKY_PASSWORD=your-app-password

# ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ (опционально)
OPENAI_API_KEY=your-openai-key-optional

# СИСТЕМНЫЕ НАСТРОЙКИ
PYTHONPATH=/home/$(whoami)/BlueSky-Bot
LOG_LEVEL=INFO
EOF
        print_success "Файл .env создан"
    else
        print_warning "Файл .env уже существует"
    fi
    
    # Создаем скрипт запуска
    cat > start_bot.sh << 'EOF'
#!/bin/bash

# BlueSky Bot Starter Script
# ==========================

cd "$(dirname "$0")"

# Загружаем переменные окружения
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Активируем виртуальное окружение
source venv/bin/activate

# Запускаем бота
echo "🤖 Запуск BlueSky Bot..."
python3 bluesky_bot_v2.py
EOF
    
    chmod +x start_bot.sh
    
    print_success "Скрипт запуска создан"
}

# Создание systemd сервиса
create_systemd_service() {
    print_header "Создание systemd сервиса"
    
    SERVICE_FILE="/etc/systemd/system/bluesky-bot.service"
    
    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=BlueSky Bot
After=network.target
Wants=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$HOME/BlueSky-Bot
EnvironmentFile=$HOME/BlueSky-Bot/.env
ExecStart=$HOME/BlueSky-Bot/venv/bin/python $HOME/BlueSky-Bot/bluesky_bot_v2.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bluesky-bot

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$HOME/BlueSky-Bot

[Install]
WantedBy=multi-user.target
EOF
    
    # Перезагружаем systemd
    sudo systemctl daemon-reload
    
    print_success "Systemd сервис создан"
    print_info "Сервис будет доступен как: sudo systemctl start bluesky-bot"
}

# Настройка логирования
setup_logging() {
    print_header "Настройка логирования"
    
    cd "$HOME/BlueSky-Bot"
    
    # Создаем директорию для логов
    mkdir -p logs
    
    # Настраиваем ротацию логов
    sudo tee /etc/logrotate.d/bluesky-bot > /dev/null << EOF
$HOME/BlueSky-Bot/bot.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    copytruncate
    su $(whoami) $(whoami)
}
EOF
    
    print_success "Логирование настроено (ротация каждые 7 дней)"
}

# Создание утилит управления
create_management_scripts() {
    print_header "Создание утилит управления"
    
    cd "$HOME/BlueSky-Bot"
    
    # Скрипт мониторинга
    cat > monitor.sh << 'EOF'
#!/bin/bash

# BlueSky Bot Monitor
# ===================

BOT_DIR="$HOME/BlueSky-Bot"
cd "$BOT_DIR"

echo "🤖 BlueSky Bot Status Monitor"
echo "=============================="

# Проверяем статус сервиса
if systemctl is-active --quiet bluesky-bot; then
    echo "✅ Сервис: ЗАПУЩЕН"
else
    echo "❌ Сервис: ОСТАНОВЛЕН"
fi

# Показываем последние логи
echo -e "\n📋 Последние 10 строк лога:"
echo "-----------------------------"
tail -n 10 bot.log 2>/dev/null || echo "Логи не найдены"

# Показываем использование ресурсов
echo -e "\n💾 Использование ресурсов:"
echo "---------------------------"
ps aux | grep -E "(python.*bluesky_bot|PID)" | grep -v grep

# Показываем размер лога
if [ -f "bot.log" ]; then
    LOG_SIZE=$(du -h bot.log | cut -f1)
    echo -e "\n📄 Размер лога: $LOG_SIZE"
fi
EOF
    
    chmod +x monitor.sh
    
    # Скрипт обновления
    cat > update.sh << 'EOF'
#!/bin/bash

# BlueSky Bot Update Script
# =========================

echo "🔄 Обновление BlueSky Bot..."

cd "$HOME/BlueSky-Bot"

# Останавливаем бота
echo "⏹️  Останавливаем бота..."
sudo systemctl stop bluesky-bot

# Сохраняем конфигурацию
cp .env .env.backup

# Получаем обновления
echo "📥 Получение обновлений из Git..."
git pull origin main

# Обновляем зависимости
echo "📦 Обновление зависимостей..."
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Восстанавливаем конфигурацию
mv .env.backup .env

# Перезапускаем бота
echo "🚀 Перезапуск бота..."
sudo systemctl start bluesky-bot

echo "✅ Обновление завершено!"
EOF
    
    chmod +x update.sh
    
    # Скрипт полного управления
    cat > manage.sh << 'EOF'
#!/bin/bash

# BlueSky Bot Management Script
# =============================

case "$1" in
    start)
        echo "🚀 Запуск BlueSky Bot..."
        sudo systemctl start bluesky-bot
        sudo systemctl status bluesky-bot --no-pager
        ;;
    stop)
        echo "⏹️  Остановка BlueSky Bot..."
        sudo systemctl stop bluesky-bot
        ;;
    restart)
        echo "🔄 Перезапуск BlueSky Bot..."
        sudo systemctl restart bluesky-bot
        sudo systemctl status bluesky-bot --no-pager
        ;;
    status)
        sudo systemctl status bluesky-bot --no-pager
        ;;
    logs)
        echo "📋 Последние логи BlueSky Bot:"
        journalctl -u bluesky-bot -f
        ;;
    config)
        echo "⚙️  Редактирование конфигурации..."
        nano .env
        ;;
    monitor)
        ./monitor.sh
        ;;
    update)
        ./update.sh
        ;;
    *)
        echo "BlueSky Bot Management"
        echo "====================="
        echo "Использование: $0 {start|stop|restart|status|logs|config|monitor|update}"
        echo ""
        echo "Команды:"
        echo "  start   - Запустить бота"
        echo "  stop    - Остановить бота"
        echo "  restart - Перезапустить бота"
        echo "  status  - Статус сервиса"
        echo "  logs    - Просмотр логов в реальном времени"
        echo "  config  - Редактировать конфигурацию"
        echo "  monitor - Мониторинг состояния"
        echo "  update  - Обновить бота из Git"
        ;;
esac
EOF
    
    chmod +x manage.sh
    
    print_success "Утилиты управления созданы"
}

# Финальная настройка
final_setup() {
    print_header "Финальная настройка"
    
    cd "$HOME/BlueSky-Bot"
    
    # Делаем бота доступным глобально
    echo "export PATH=\"\$PATH:$HOME/BlueSky-Bot\"" >> ~/.bashrc
    
    # Создаем алиасы для удобства
    cat >> ~/.bashrc << EOF

# BlueSky Bot Aliases
alias bot-start='cd $HOME/BlueSky-Bot && ./manage.sh start'
alias bot-stop='cd $HOME/BlueSky-Bot && ./manage.sh stop'
alias bot-restart='cd $HOME/BlueSky-Bot && ./manage.sh restart'
alias bot-status='cd $HOME/BlueSky-Bot && ./manage.sh status'
alias bot-logs='cd $HOME/BlueSky-Bot && ./manage.sh logs'
alias bot-config='cd $HOME/BlueSky-Bot && ./manage.sh config'
alias bot-monitor='cd $HOME/BlueSky-Bot && ./manage.sh monitor'
alias bot-update='cd $HOME/BlueSky-Bot && ./manage.sh update'
EOF
    
    print_success "Глобальные команды настроены"
}

# Показ инструкций
show_instructions() {
    print_header "🎉 Установка завершена!"
    
    echo -e "${GREEN}"
    cat << 'EOF'
╔═══════════════════════════════════════════════════════════════╗
║                    BlueSky Bot установлен!                   ║
╚═══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
    
    print_info "СЛЕДУЮЩИЕ ШАГИ:"
    echo ""
    echo "1️⃣  Настройте конфигурацию:"
    echo "   cd ~/BlueSky-Bot && nano .env"
    echo ""
    echo "2️⃣  Введите ваши данные BlueSky:"
    echo "   BLUESKY_HANDLE=ваш-бот.bsky.social"
    echo "   BLUESKY_PASSWORD=ваш-пароль-приложения"
    echo ""
    echo "3️⃣  Запустите бота:"
    echo "   bot-start"
    echo ""
    
    print_info "ПОЛЕЗНЫЕ КОМАНДЫ:"
    echo ""
    echo "🚀 bot-start     - Запустить бота"
    echo "⏹️  bot-stop      - Остановить бота"
    echo "🔄 bot-restart   - Перезапустить бота"
    echo "📊 bot-status    - Статус бота"
    echo "📋 bot-logs      - Просмотр логов"
    echo "⚙️  bot-config    - Редактировать настройки"
    echo "📱 bot-monitor   - Мониторинг состояния"
    echo "🔄 bot-update    - Обновить бота"
    echo ""
    
    print_info "РАСПОЛОЖЕНИЕ ФАЙЛОВ:"
    echo ""
    echo "📁 Бот:           ~/BlueSky-Bot/"
    echo "⚙️  Конфигурация:  ~/BlueSky-Bot/.env"
    echo "📄 Логи:          ~/BlueSky-Bot/bot.log"
    echo "🔧 Управление:    ~/BlueSky-Bot/manage.sh"
    echo ""
    
    print_warning "ВАЖНО: Не забудьте перезагрузить терминал или выполните:"
    echo "source ~/.bashrc"
    echo ""
    
    print_success "Установка завершена! Удачного использования! 🤖"
}

# =================================================================
# ОСНОВНОЙ ПРОЦЕСС УСТАНОВКИ
# =================================================================

main() {
    clear
    
    echo -e "${BLUE}"
    cat << 'EOF'
╔═══════════════════════════════════════════════════════════════╗
║                BlueSky Bot Auto-Installer                    ║
║              для Ubuntu Server 24.04.2                      ║
╚═══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
    
    print_info "Начинаем автоматическую установку..."
    sleep 2
    
    check_user
    check_os
    install_system_deps
    clone_repository
    setup_python_env
    setup_configuration
    create_systemd_service
    setup_logging
    create_management_scripts
    final_setup
    show_instructions
}

# Запуск основной функции
main "$@" 