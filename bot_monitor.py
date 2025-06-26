#!/usr/bin/env python3
"""
Скрипт мониторинга BlueSky бота
Проверяет heartbeat и логи для выявления зависаний
"""

import os
import sys
import time
import subprocess
from datetime import datetime, timedelta

def check_heartbeat():
    """Проверяет файл heartbeat бота"""
    heartbeat_file = 'bot_heartbeat.txt'
    
    if not os.path.exists(heartbeat_file):
        return False, "Файл heartbeat не найден"
    
    try:
        with open(heartbeat_file, 'r') as f:
            lines = f.readlines()
            if not lines:
                return False, "Файл heartbeat пуст"
        
        last_heartbeat_str = lines[0].strip()
        last_heartbeat = datetime.fromisoformat(last_heartbeat_str)
        
        time_diff = (datetime.now() - last_heartbeat).total_seconds()
        
        if time_diff > 1200:  # 20 минут
            return False, f"Heartbeat устарел на {time_diff/60:.1f} минут"
        elif time_diff > 900:  # 15 минут
            return True, f"ПРЕДУПРЕЖДЕНИЕ: Heartbeat {time_diff/60:.1f} минут назад"
        else:
            return True, f"OK: Последний heartbeat {time_diff/60:.1f} минут назад"
            
    except Exception as e:
        return False, f"Ошибка чтения heartbeat: {e}"

def check_process():
    """Проверяет запущен ли процесс бота"""
    try:
        result = subprocess.run(['pgrep', '-f', 'bluesky_bot_v2.py'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            return True, f"Процесс работает (PID: {', '.join(pids)})"
        else:
            return False, "Процесс не найден"
    except Exception as e:
        return False, f"Ошибка проверки процесса: {e}"

def check_logs():
    """Проверяет последние записи в логе"""
    log_file = 'bot.log'
    
    if not os.path.exists(log_file):
        return False, "Лог файл не найден"
    
    try:
        # Читаем последние 10 строк
        result = subprocess.run(['tail', '-n', '10', log_file], 
                              capture_output=True, text=True)
        
        if result.returncode != 0:
            return False, "Не удалось прочитать лог"
        
        lines = result.stdout.strip().split('\n')
        if not lines:
            return False, "Лог файл пуст"
        
        # Проверяем последнюю строку на время
        last_line = lines[-1]
        if '2025-' in last_line:
            # Извлекаем время из строки лога
            time_part = last_line.split(' - ')[0]
            try:
                log_time = datetime.strptime(time_part, '%Y-%m-%d %H:%M:%S,%f')
                time_diff = (datetime.now() - log_time).total_seconds()
                
                if time_diff > 1800:  # 30 минут
                    return False, f"Последняя запись в логе {time_diff/60:.1f} минут назад"
                else:
                    return True, f"Последняя запись {time_diff/60:.1f} минут назад"
            except:
                return True, "Лог активен (время не распознано)"
        
        return True, "Лог содержит записи"
        
    except Exception as e:
        return False, f"Ошибка чтения лога: {e}"

def restart_bot():
    """Перезапускает бота через systemctl"""
    try:
        print("🔄 Перезапуск бота...")
        subprocess.run(['sudo', 'systemctl', 'restart', 'bluesky-bot.service'], 
                      check=True)
        time.sleep(10)  # Ждем запуска
        return True
    except Exception as e:
        print(f"❌ Ошибка перезапуска: {e}")
        return False

def main():
    """Основная функция мониторинга"""
    print(f"🔍 Мониторинг BlueSky бота - {datetime.now()}")
    print("=" * 50)
    
    # Проверяем все системы
    checks = [
        ("Процесс", check_process()),
        ("Heartbeat", check_heartbeat()),
        ("Логи", check_logs())
    ]
    
    all_ok = True
    critical_issues = 0
    
    for name, (status, message) in checks:
        status_icon = "✅" if status else "❌"
        print(f"{status_icon} {name}: {message}")
        
        if not status:
            all_ok = False
            if name in ["Процесс", "Heartbeat"]:
                critical_issues += 1
    
    print("=" * 50)
    
    if all_ok:
        print("✅ Все системы работают нормально")
        return 0
    elif critical_issues >= 2:
        print("🚨 КРИТИЧЕСКИЕ ПРОБЛЕМЫ! Перезапуск бота...")
        if restart_bot():
            print("✅ Бот перезапущен")
            return 0
        else:
            print("❌ Не удалось перезапустить бота")
            return 1
    else:
        print("⚠️ Обнаружены проблемы, но не критические")
        return 0

if __name__ == "__main__":
    sys.exit(main()) 