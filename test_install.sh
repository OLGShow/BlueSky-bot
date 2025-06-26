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

# Функция для красивого вывода
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

# Основная функция установки
main() {
    print_header
    
    print_step "Проверка системных требований..."
    
    # Проверяем Ubuntu
    if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
        print_error "Эта установка предназначена для Ubuntu Server!"
        exit 1
    fi
    
    print_success "Ubuntu detected"
    
    # Проверяем права sudo
    if [ "$EUID" -eq 0 ]; then
        print_error "Не запускайте под root! Используйте обычного пользователя с sudo."
        exit 1
    fi
    
    if ! sudo -n true 2>/dev/null; then
        print_error "Пользователь должен иметь права sudo без запроса пароля"
        exit 1
    fi
    
    print_success "Права пользователя проверены"
    
    print_step "Установка BlueSky Bot..."
    echo "Тест успешно создан!"
}

main "$@" 