import json
import logging
from datetime import datetime, timedelta

try:
    from state_service import AtomicConfigWriter
except ImportError:
    AtomicConfigWriter = None

logger = logging.getLogger(__name__)

class BotLearningModule:
    def __init__(self, memory, config_file='bot_config.json'):
        self.memory = memory
        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self):
        with open(self.config_file, 'r') as f:
            return json.load(f)

    def save_config(self):
        if AtomicConfigWriter:
            AtomicConfigWriter.save(self.config, self.config_file)
        else:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

    def analyze_performance_and_learn(self):
        """
        Анализирует производительность постов и корректирует веса стратегий.
        Это наш 'SEAL' цикл.
        """
        logger.info("🧠 Запуск цикла самообучения бота...")
        
        analysis_period = self.config['learning_parameters']['analysis_period_hours']
        recent_posts = [
            p for p in self.memory.successful_posts 
            if datetime.fromisoformat(p['timestamp']) > datetime.now() - timedelta(hours=analysis_period)
        ]

        if not recent_posts:
            logger.info("📊 Недостаточно свежих постов для анализа. Пропускаем обучение.")
            return

        # Анализируем, какие типы постов работают лучше
        performance_scores = {strategy: [] for strategy in self.config['post_strategies']}

        for post in recent_posts:
            post_type = post.get('type')
            # Ваша логика для получения uri, cid, и затем производительности
            # Это потребует доработки для получения реальных лайков/репостов
            # Здесь мы симулируем производительность
            likes = post.get('likes', 0) # Предполагается, что вы будете обновлять это поле
            reposts = post.get('reposts', 0) # Аналогично
            
            score = likes + (reposts * 2) # Простая формула производительности
            
            strategy_name = self._get_strategy_name_by_type(post_type)
            if strategy_name in performance_scores:
                performance_scores[strategy_name].append(score)

        # Вычисляем среднюю производительность
        avg_performance = {}
        for strategy, scores in performance_scores.items():
            if scores:
                avg_performance[strategy] = sum(scores) / len(scores)
            else:
                avg_performance[strategy] = 0
        
        logger.info(f"📈 Средняя производительность стратегий: {avg_performance}")

        # Корректируем веса
        self._adjust_strategy_weights(avg_performance)
        
        self.save_config()
        logger.info("✅ Цикл самообучения завершен. Конфигурация обновлена.")

    def _get_strategy_name_by_type(self, content_type: str) -> str:
        # ИСПРАВЛЕНО: синхронизировано с bot_config.json и устранен дубликат
        type_to_strategy_map = {
            'news': '_create_quality_news_post',
            'personal': '_create_personal_opinion_post',
            'ai': '_create_quality_ai_insight',
            'tip': '_create_quality_tip_post',
            'discussion': '_create_quality_discussion',
            'motivational': '_create_personal_opinion_post',
            'emergency': '_create_personal_opinion_post',
            'list': '_create_quality_tip_post',
            'poll': '_create_quality_discussion',
            'general': '_create_personal_opinion_post'
        }
        return type_to_strategy_map.get(content_type, '_create_personal_opinion_post')

    def _adjust_strategy_weights(self, avg_performance):
        """Логика 'само-правки' - изменение весов стратегий."""
        total_score = sum(avg_performance.values())
        if total_score == 0:
            logger.info("⚠️ Общая производительность равна нулю, веса не изменены.")
            return

        learning_rate = self.config['learning_parameters']['learning_rate']
        strategies = self.config['post_strategies']
        
        # Перераспределяем долю от менее успешных к более успешным
        total_weight_change = 0
        weight_changes = {}

        # Находим самую плохую и хорошую стратегии
        worst_strategy = min(avg_performance, key=avg_performance.get)
        best_strategy = max(avg_performance, key=avg_performance.get)

        if worst_strategy != best_strategy and strategies[worst_strategy] > 0.05:
            change = strategies[worst_strategy] * learning_rate
            
            logger.info(f"💡 Само-правка: Уменьшаем '{worst_strategy}' и увеличиваем '{best_strategy}' на {change:.4f}")
            
            strategies[worst_strategy] -= change
            strategies[best_strategy] += change

            # Нормализуем веса, чтобы их сумма оставалась 1
            current_total = sum(strategies.values())
            for s in strategies:
                strategies[s] /= current_total
        
        self.config['post_strategies'] = strategies
        logger.info(f"🧠 Новые веса стратегий: {self.config['post_strategies']}")

if __name__ == '__main__':
    # Пример использования
    # Нужна симуляция памяти бота
    class MockMemory:
        successful_posts = [
            {'timestamp': datetime.now().isoformat(), 'type': 'ai', 'likes': 10, 'reposts': 2},
            {'timestamp': datetime.now().isoformat(), 'type': 'tip', 'likes': 2, 'reposts': 0},
        ]
    
    learning_module = BotLearningModule(MockMemory())
    learning_module.analyze_performance_and_learn()
    print("Проверьте bot_config.json на наличие изменений.") 