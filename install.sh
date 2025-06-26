#!/bin/bash

# BlueSky Bot - Автоматическая установка для Ubuntu Server 24.04.2
# Версия: 3.0 - Полностью автоматизированная установка

set -e  # Выход при любой ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Конфигурация
INSTALL_DIR="$HOME/BlueSky-Bot"
SERVICE_NAME="bluesky-bot"
REPO_URL="https://github.com/OLGShow/BlueSky-bot.git"
PYTHON_VERSION="3.12"

# Функции для красивого вывода
print_header() {
    echo -e "${PURPLE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║${WHITE}                    BlueSky Bot Installer v3.0                ║${NC}"
    echo -e "${PURPLE}║${CYAN}            Автоматическая установка для Ubuntu Server         ║${NC}"
    echo -e "${PURPLE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Проверка системных требований
check_requirements() {
    print_step "Проверка системных требований..."
    
    # Проверяем Ubuntu
    if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
        print_error "Эта установка предназначена для Ubuntu Server!"
        exit 1
    fi
    
    # Проверяем версию Ubuntu
    UBUNTU_VERSION=$(lsb_release -rs 2>/dev/null || echo "unknown")
    if [[ "$UBUNTU_VERSION" < "20.04" ]]; then
        print_warning "Рекомендуется Ubuntu 20.04 или новее (найдено: $UBUNTU_VERSION)"
    else
        print_success "Ubuntu $UBUNTU_VERSION"
    fi
    
    # Проверяем права sudo
    if [ "$EUID" -eq 0 ]; then
        print_error "Не запускайте под root! Используйте обычного пользователя с sudo."
        exit 1
    fi
    
    if ! sudo -n true 2>/dev/null; then
        print_error "Пользователь должен иметь права sudo без запроса пароля"
        print_error "Выполните: echo '$USER ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/$USER"
        exit 1
    fi
    
    print_success "Права пользователя проверены"
    
    # Проверяем доступность интернета
    if ! ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        print_error "Нет подключения к интернету!"
        exit 1
    fi
    
    print_success "Подключение к интернету активно"
    
    # Проверяем свободное место на диске (минимум 2GB)
    AVAILABLE_SPACE=$(df "$HOME" | awk 'NR==2 {print $4}')
    if [ "$AVAILABLE_SPACE" -lt 2097152 ]; then
        print_warning "Мало свободного места на диске (< 2GB)"
    else
        print_success "Достаточно свободного места на диске"
    fi
}

# Установка системных зависимостей
install_system_dependencies() {
    print_step "Обновление системы и установка зависимостей..."
    
    # Обновляем списки пакетов
    sudo apt update -qq
    
    # Устанавливаем необходимые пакеты
    sudo apt install -y \
        software-properties-common \
        apt-transport-https \
        ca-certificates \
        curl \
        wget \
        git \
        build-essential \
        libssl-dev \
        libffi-dev \
        python3-dev \
        python3-pip \
        python3-venv \
        systemd \
        logrotate \
        nano \
        htop \
        unzip
    
    print_success "Системные зависимости установлены"
}

# Установка Python 3.12
install_python() {
    print_step "Установка Python $PYTHON_VERSION..."
    
    # Проверяем, есть ли уже нужная версия Python
    if command -v python3.12 >/dev/null 2>&1; then
        print_success "Python 3.12 уже установлен"
        return
    fi
    
    # Добавляем PPA для новых версий Python
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update -qq
    
    # Устанавливаем Python 3.12
    sudo apt install -y python3.12 python3.12-venv python3.12-dev
    
    # Проверяем установку
    if python3.12 --version >/dev/null 2>&1; then
        print_success "Python 3.12 успешно установлен"
    else
        print_error "Ошибка установки Python 3.12"
        exit 1
    fi
}

# Клонирование репозитория
clone_repository() {
    print_step "Клонирование репозитория..."
    
    # Удаляем старую папку если существует
    if [ -d "$INSTALL_DIR" ]; then
        print_warning "Папка $INSTALL_DIR уже существует. Удаляем..."
        rm -rf "$INSTALL_DIR"
    fi
    
    # Клонируем репозиторий
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    print_success "Репозиторий клонирован в $INSTALL_DIR"
}

# Настройка Python виртуального окружения
setup_python_environment() {
    print_step "Создание Python виртуального окружения..."
    
    cd "$INSTALL_DIR"
    
    # Создаем виртуальное окружение
    python3.12 -m venv venv
    
    # Активируем окружение и устанавливаем зависимости
    source venv/bin/activate
    
    # Обновляем pip
    pip install --upgrade pip
    
    # Устанавливаем зависимости
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        print_success "Python зависимости установлены"
    else
        print_error "Файл requirements.txt не найден!"
        exit 1
    fi
}

# Создание конфигурационного файла
create_config() {
    print_step "Создание конфигурационного файла..."
    
    cd "$INSTALL_DIR"
    
    # Копируем шаблон конфигурации
    if [ -f "env.example" ]; then
        cp env.example .env
        print_success "Создан файл .env из шаблона"
        print_warning "ВАЖНО: Отредактируйте файл $INSTALL_DIR/.env с вашими учетными данными!"
    else
        print_error "Файл env.example не найден!"
        exit 1
    fi
}

# Создание systemd службы
create_systemd_service() {
    print_step "Создание systemd службы..."
    
    # Создаем службу из шаблона
    if [ -f "$INSTALL_DIR/systemd/bluesky-bot.service" ]; then
        # Заменяем пути в шаблоне службы
        sed "s|/home/ubuntu/BlueSky-Bot|$INSTALL_DIR|g" "$INSTALL_DIR/systemd/bluesky-bot.service" > "/tmp/$SERVICE_NAME.service"
        sed -i "s|User=ubuntu|User=$USER|g" "/tmp/$SERVICE_NAME.service"
        
        # Копируем службу в systemd
        sudo cp "/tmp/$SERVICE_NAME.service" "/etc/systemd/system/"
        sudo systemctl daemon-reload
        sudo systemctl enable "$SERVICE_NAME"
        
        print_success "Systemd служба создана и включена"
    else
        print_error "Шаблон службы не найден!"
        exit 1
    fi
}

# Создание скриптов управления
create_management_scripts() {
    print_step "Создание скриптов управления..."
    
    cd "$INSTALL_DIR"
    
    # Главный скрипт управления
    cat > manage.sh << 'EOF'
#!/bin/bash

SERVICE_NAME="bluesky-bot"
INSTALL_DIR="$HOME/BlueSky-Bot"

case "$1" in
    start)
        echo "🚀 Запуск BlueSky Bot..."
        sudo systemctl start $SERVICE_NAME
        ;;
    stop)
        echo "🛑 Остановка BlueSky Bot..."
        sudo systemctl stop $SERVICE_NAME
        ;;
    restart)
        echo "🔄 Перезапуск BlueSky Bot..."
        sudo systemctl restart $SERVICE_NAME
        ;;
    status)
        echo "📊 Статус BlueSky Bot:"
        sudo systemctl status $SERVICE_NAME --no-pager
        ;;
    logs)
        echo "📋 Логи BlueSky Bot:"
        sudo journalctl -u $SERVICE_NAME -f --no-pager
        ;;
    config)
        echo "⚙️ Редактирование конфигурации..."
        nano $INSTALL_DIR/.env
        ;;
    monitor)
        echo "👁️ Мониторинг BlueSky Bot..."
        $INSTALL_DIR/monitor.sh
        ;;
    update)
        echo "🔄 Обновление BlueSky Bot..."
        $INSTALL_DIR/update.sh
        ;;
    *)
        echo "BlueSky Bot - Управление ботом"
        echo "Использование: $0 {start|stop|restart|status|logs|config|monitor|update}"
        exit 1
        ;;
esac
EOF

    # Скрипт мониторинга
    cat > monitor.sh << 'EOF'
#!/bin/bash

SERVICE_NAME="bluesky-bot"
LOG_FILE="$HOME/BlueSky-Bot/bot.log"

echo "🤖 BlueSky Bot - Мониторинг"
echo "================================"

# Статус службы
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "✅ Служба: АКТИВНА"
else
    echo "❌ Служба: НЕАКТИВНА"
fi

# Время работы
UPTIME=$(systemctl show $SERVICE_NAME --property=ActiveEnterTimestamp --value)
if [ ! -z "$UPTIME" ]; then
    echo "⏰ Запущена: $UPTIME"
fi

# Использование ресурсов
echo ""
echo "📊 Использование ресурсов:"
ps aux | grep "bluesky_bot_v2.py" | grep -v grep | awk '{printf "   CPU: %s%%, RAM: %s%%\n", $3, $4}'

# Последние логи
echo ""
echo "📋 Последние логи:"
if [ -f "$LOG_FILE" ]; then
    tail -10 "$LOG_FILE"
else
    echo "   Файл лога не найден"
fi

echo ""
echo "Для выхода нажмите Ctrl+C"
echo "Для просмотра логов в реальном времени: ./manage.sh logs"
EOF

    # Скрипт обновления
    cat > update.sh << 'EOF'
#!/bin/bash

SERVICE_NAME="bluesky-bot"
INSTALL_DIR="$HOME/BlueSky-Bot"

echo "🔄 Обновление BlueSky Bot..."

# Останавливаем службу
sudo systemctl stop $SERVICE_NAME

# Сохраняем конфигурацию
cp $INSTALL_DIR/.env /tmp/bluesky-bot.env.backup

# Переходим в папку и обновляем
cd $INSTALL_DIR
git pull origin main

# Восстанавливаем конфигурацию
cp /tmp/bluesky-bot.env.backup $INSTALL_DIR/.env

# Обновляем зависимости
source venv/bin/activate
pip install --upgrade -r requirements.txt

# Перезапускаем службу
sudo systemctl start $SERVICE_NAME

echo "✅ Обновление завершено!"
EOF

    # Простой скрипт запуска
    cat > start_bot.sh << 'EOF'
#!/bin/bash
cd "$HOME/BlueSky-Bot"
source venv/bin/activate
python bluesky_bot_v2.py
EOF

    # Делаем скрипты исполняемыми
    chmod +x manage.sh monitor.sh update.sh start_bot.sh
    
    print_success "Скрипты управления созданы"
}

# Создание глобальных команд
create_global_commands() {
    print_step "Создание глобальных команд..."
    
    # Создаем папку для локальных бинарников если не существует
    mkdir -p "$HOME/.local/bin"
    
    # Добавляем в PATH если еще не добавлено
    if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        export PATH="$HOME/.local/bin:$PATH"
    fi
    
    # Создаем символические ссылки
    ln -sf "$INSTALL_DIR/manage.sh" "$HOME/.local/bin/bot-manage"
    ln -sf "$INSTALL_DIR/monitor.sh" "$HOME/.local/bin/bot-monitor"
    ln -sf "$INSTALL_DIR/update.sh" "$HOME/.local/bin/bot-update"
    
    # Создаем удобные команды
    cat > "$HOME/.local/bin/bot-start" << EOF
#!/bin/bash
$INSTALL_DIR/manage.sh start
EOF

    cat > "$HOME/.local/bin/bot-stop" << EOF
#!/bin/bash
$INSTALL_DIR/manage.sh stop
EOF

    cat > "$HOME/.local/bin/bot-restart" << EOF
#!/bin/bash
$INSTALL_DIR/manage.sh restart
EOF

    cat > "$HOME/.local/bin/bot-status" << EOF
#!/bin/bash
$INSTALL_DIR/manage.sh status
EOF

    cat > "$HOME/.local/bin/bot-logs" << EOF
#!/bin/bash
$INSTALL_DIR/manage.sh logs
EOF

    cat > "$HOME/.local/bin/bot-config" << EOF
#!/bin/bash
$INSTALL_DIR/manage.sh config
EOF

    # Делаем команды исполняемыми
    chmod +x "$HOME/.local/bin/bot-"*
    
    print_success "Глобальные команды созданы"
}

# Настройка ротации логов
setup_log_rotation() {
    print_step "Настройка ротации логов..."
    
    cat > "/tmp/bluesky-bot-logs" << EOF
$INSTALL_DIR/bot.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 $USER $USER
    postrotate
        systemctl reload $SERVICE_NAME > /dev/null 2>&1 || true
    endscript
}
EOF
    
    sudo mv "/tmp/bluesky-bot-logs" "/etc/logrotate.d/"
    
    print_success "Ротация логов настроена"
}

# Заключительная настройка
final_setup() {
    print_step "Финальная настройка..."
    
    # Устанавливаем правильные права доступа
    chown -R "$USER:$USER" "$INSTALL_DIR"
    chmod -R 755 "$INSTALL_DIR"
    
    # Создаем папку для логов если не существует
    mkdir -p "$INSTALL_DIR/logs"
    
    print_success "Права доступа настроены"
}

# Вывод инструкций
print_instructions() {
    print_step "🎉 Установка завершена!"
    echo ""
    echo -e "${GREEN}BlueSky Bot успешно установлен!${NC}"
    echo ""
    echo -e "${YELLOW}Следующие шаги:${NC}"
    echo "1. Отредактируйте конфигурацию:"
    echo -e "   ${CYAN}bot-config${NC} или ${CYAN}nano $INSTALL_DIR/.env${NC}"
    echo ""
    echo "2. Укажите ваши учетные данные BlueSky:"
    echo "   - BLUESKY_HANDLE=ваш.handle.bsky.social"
    echo "   - BLUESKY_PASSWORD=ваш-пароль-приложения"
    echo ""
    echo "3. Запустите бота:"
    echo -e "   ${CYAN}bot-start${NC}"
    echo ""
    echo -e "${YELLOW}Доступные команды:${NC}"
    echo -e "   ${CYAN}bot-start${NC}    - Запуск бота"
    echo -e "   ${CYAN}bot-stop${NC}     - Остановка бота"
    echo -e "   ${CYAN}bot-restart${NC}  - Перезапуск бота"
    echo -e "   ${CYAN}bot-status${NC}   - Статус бота"
    echo -e "   ${CYAN}bot-logs${NC}     - Просмотр логов"
    echo -e "   ${CYAN}bot-config${NC}   - Редактирование конфигурации"
    echo -e "   ${CYAN}bot-monitor${NC}  - Мониторинг бота"
    echo -e "   ${CYAN}bot-update${NC}   - Обновление бота"
    echo ""
    echo -e "${GREEN}Удачного использования BlueSky Bot! 🤖${NC}"
}

# Основная функция установки
main() {
    print_header
    
    check_requirements
    install_system_dependencies
    install_python
    clone_repository
    setup_python_environment
    create_config
    create_systemd_service
    create_management_scripts
    create_global_commands
    setup_log_rotation
    final_setup
    print_instructions
    
    echo ""
    print_success "Установка завершена успешно!"
}

# Проверяем аргументы командной строки
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "BlueSky Bot - Автоматическая установка"
    echo "Использование: $0 [опции]"
    echo ""
    echo "Опции:"
    echo "  -h, --help     Показать эту справку"
    echo "  --no-service   Не создавать systemd службу"
    echo ""
    echo "Этот скрипт автоматически устанавливает BlueSky Bot на Ubuntu Server."
    exit 0
fi

# Запускаем основную функцию
main "$@" 