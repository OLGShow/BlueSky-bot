#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dynamic Content System for BlueSky Bot
Real audience-focused: 53.4% general public, 27.5% tech, 12.4% creative
With trending topics tracker and 50+ content variations
"""

import asyncio
import json
import random
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import Counter, defaultdict
import logging
from atproto import AsyncClient

logger = logging.getLogger(__name__)

class BlueSkyTrendingTracker:
    """Tracks trending topics and hashtags from BlueSky for dynamic content generation"""
    
    def __init__(self, client: AsyncClient):
        self.client = client
        self.trending_cache = {}
        self.cache_expiry = timedelta(hours=2)
        self.last_update = None
    
    async def get_trending_topics(self, limit: int = 20) -> List[Dict]:
        """Get currently trending topics from BlueSky"""
        try:
            # Check cache first
            if (self.last_update and 
                datetime.now() - self.last_update < self.cache_expiry and
                self.trending_cache):
                return self.trending_cache.get('topics', [])
            
            logger.info("🔍 Fetching trending topics from BlueSky...")
            
            # Get recent timeline posts
            timeline = await self.client.app.bsky.feed.get_timeline({'limit': 100})
            
            # Extract hashtags and topics
            hashtags = []
            topics = []
            
            for post in timeline.feed:
                if hasattr(post.post, 'record') and hasattr(post.post.record, 'text'):
                    text = post.post.record.text
                    
                    # Extract hashtags
                    post_hashtags = re.findall(r'#(\w+)', text)
                    hashtags.extend([tag.lower() for tag in post_hashtags])
                    
                    # Extract potential topics (noun phrases)
                    words = re.findall(r'\b[A-Za-z]{4,}\b', text)
                    topics.extend([word.lower() for word in words])
            
            # Count and rank
            hashtag_counts = Counter(hashtags).most_common(limit)
            topic_counts = Counter(topics).most_common(limit)
            
            trending_data = {
                'hashtags': [{'tag': tag, 'count': count} for tag, count in hashtag_counts],
                'topics': [{'topic': topic, 'count': count} for topic, count in topic_counts],
                'timestamp': datetime.now().isoformat()
            }
            
            # Update cache
            self.trending_cache = trending_data
            self.last_update = datetime.now()
            
            logger.info(f"✅ Found {len(hashtag_counts)} trending hashtags, {len(topic_counts)} topics")
            return trending_data['topics']
            
        except Exception as e:
            logger.error(f"❌ Error fetching trending topics: {e}")
            return []
    
    async def get_trending_hashtags(self) -> List[str]:
        """Get trending hashtags for posts"""
        try:
            await self.get_trending_topics()  # Update cache
            hashtags = self.trending_cache.get('hashtags', [])
            return [f"#{item['tag']}" for item in hashtags[:10]]
        except:
            return ["#trending", "#discussion", "#thoughts"]

class DynamicContentGenerator:
    """Advanced content generation with 53.4% general focus"""
    
    def __init__(self, trending_tracker: BlueSkyTrendingTracker):
        self.trending_tracker = trending_tracker
        self.content_categories = self._initialize_content_categories()
        self.dynamic_templates = self._initialize_dynamic_templates()
    
    def _initialize_content_categories(self) -> Dict:
        """Initialize content categories based on real BlueSky audience analysis"""
        return {
            # 53.4% GENERAL PUBLIC CONTENT
            "lifestyle_wellness": {
                "weight": 0.18,  # 18% of all content
                "topics": [
                    "morning routines that actually work",
                    "simple mindfulness practices",
                    "work-life balance strategies",
                    "healthy habits for busy people",
                    "personal growth milestones",
                    "dealing with daily stress",
                    "building meaningful relationships",
                    "finding purpose in everyday life",
                    "small wins that matter",
                    "gratitude and appreciation",
                    "self-care without guilt",
                    "embracing change and uncertainty",
                    "productivity without burnout",
                    "digital wellness boundaries",
                    "creating peaceful spaces",
                    "time management reality",
                    "energy vs motivation",
                    "saying no with kindness"
                ]
            },
            "culture_society": {
                "weight": 0.15,  # 15% of all content
                "topics": [
                    "generational differences in communication",
                    "social media impact on real connections",
                    "art that moves people",
                    "music discoveries worth sharing",
                    "books that changed perspectives",
                    "travel experiences vs expectations",
                    "local community observations",
                    "cultural trends worth discussing",
                    "language evolution in digital age",
                    "traditional vs modern values",
                    "celebrating diverse perspectives",
                    "human connection in digital world",
                    "storytelling across cultures",
                    "food and cultural identity",
                    "urban vs rural experiences",
                    "generational wisdom sharing"
                ]
            },
            "creativity_inspiration": {
                "weight": 0.12,  # 12% of all content
                "topics": [
                    "creative blocks and breakthroughs",
                    "finding inspiration in ordinary moments",
                    "artistic expression in daily life",
                    "photography tips for beginners",
                    "writing thoughts and reflections",
                    "DIY projects that spark joy",
                    "music creation and appreciation",
                    "visual arts and design trends",
                    "storytelling in personal experience",
                    "creativity in problem solving",
                    "artistic challenges and growth",
                    "sharing creative discoveries",
                    "handmade vs mass produced",
                    "creative community building",
                    "inspiration from nature",
                    "artistic courage and vulnerability"
                ]
            },
            "nature_environment": {
                "weight": 0.08,  # 8% of all content
                "topics": [
                    "seasonal changes and observations",
                    "urban nature discoveries",
                    "sustainable living tips",
                    "gardening for beginners",
                    "weather patterns and moods",
                    "outdoor activities and benefits",
                    "environmental awareness",
                    "connecting with natural world",
                    "climate change personal actions",
                    "wildlife observations",
                    "green lifestyle choices",
                    "nature photography moments",
                    "seasonal eating habits",
                    "natural light and wellbeing",
                    "hiking and mindfulness",
                    "backyard biodiversity"
                ]
            },
            
            # 27.5% TECH CONTENT (Reduced from previous focus)
            "tech_innovation": {
                "weight": 0.15,  # 15% of all content
                "topics": [
                    "AI tools for everyday productivity",
                    "smartphone tips most people miss",
                    "privacy in digital age",
                    "social media algorithm insights",
                    "remote work technology setup",
                    "digital wellness and screen time",
                    "emerging tech trends worth watching",
                    "coding as creative expression",
                    "tech accessibility improvements",
                    "digital security basics",
                    "automation in daily life",
                    "future of human-computer interaction",
                    "tech minimalism approaches",
                    "learning to code at any age",
                    "digital tools for creativity",
                    "tech ethics in practice"
                ]
            },
            "professional_development": {
                "weight": 0.125,  # 12.5% of all content
                "topics": [
                    "career transitions and pivots",
                    "skill development strategies",
                    "networking authentically",
                    "remote work best practices",
                    "leadership in small teams",
                    "freelancing vs full-time work",
                    "learning new technologies",
                    "interview experiences and tips",
                    "workplace culture observations",
                    "professional growth mindset",
                    "industry trends and adaptations",
                    "work-life integration challenges",
                    "mentorship and guidance",
                    "personal branding authenticity",
                    "continuous learning strategies",
                    "collaboration in digital age"
                ]
            },
            
            # 12.4% CREATIVE CONTENT
            "creative_projects": {
                "weight": 0.08,  # 8% of all content
                "topics": [
                    "personal project journeys",
                    "creative collaboration experiences",
                    "design thinking in everyday problems",
                    "artistic experiments and failures",
                    "creative community building",
                    "inspiration sources and methods",
                    "creative tool discoveries",
                    "artistic skill development",
                    "creative business insights",
                    "balancing creativity and practicality",
                    "creative process documentation",
                    "artistic expression evolution",
                    "creative workspace setup",
                    "artistic technique sharing",
                    "creative project planning",
                    "artistic risk taking"
                ]
            },
            "arts_culture": {
                "weight": 0.044,  # 4.4% of all content
                "topics": [
                    "local art scene discoveries",
                    "cultural event experiences",
                    "artistic movements worth knowing",
                    "creative industry observations",
                    "art collecting on a budget",
                    "supporting emerging artists",
                    "cultural preservation efforts",
                    "artistic education value",
                    "cross-cultural creative exchange",
                    "art therapy and wellness",
                    "creative space organization",
                    "artistic community impact",
                    "museum and gallery experiences",
                    "street art and public space",
                    "digital art appreciation",
                    "artistic legacy and influence"
                ]
            },
            
            # TRENDING DYNAMIC CONTENT
            "trending_adaptive": {
                "weight": 0.05,  # 5% - adapts to BlueSky trends
                "topics": []  # Populated dynamically from trending tracker
            }
        }
    
    def _initialize_dynamic_templates(self) -> Dict:
        """Initialize dynamic content templates with audience-appropriate language"""
        return {
            "personal_story": [
                "Today I realized {insight}. {context} Anyone else notice this?",
                "Quick observation: {insight}. {context} What's your take?",
                "Been thinking about {insight}. {context} Share your thoughts?",
                "Random thought: {insight}. {context} Can you relate?",
                "Life lesson learned: {insight}. {context} What would you add?",
                "Something clicked today: {insight}. {context} Sound familiar?",
                "Perspective shift: {insight}. {context} What's your experience?",
                "Daily reminder: {insight}. {context} How do you handle this?",
                "Honest reflection: {insight}. {context} Anyone else struggle with this?",
                "Small epiphany: {insight}. {context} What helps you with this?",
                "Unexpected realization: {insight}. {context} Does this resonate?",
                "Something I'm learning: {insight}. {context} What's your journey?",
                "Personal discovery: {insight}. {context} How has this shown up for you?",
                "Moment of clarity: {insight}. {context} What patterns do you see?",
                "Honest moment: {insight}. {context} What's been your experience?"
            ],
            "question_starter": [
                "Genuine question: {question} {context} What's been your experience?",
                "Curious about something: {question} {context} How do you approach this?",
                "Been wondering: {question} {context} What do you think?",
                "Real talk: {question} {context} Share your perspective?",
                "Question for the community: {question} {context} What works for you?",
                "Something I'm pondering: {question} {context} Anyone have insights?",
                "Honest question: {question} {context} What's your view?",
                "Thinking out loud: {question} {context} How do you see this?",
                "Quick poll of sorts: {question} {context} What's your answer?",
                "Community wisdom needed: {question} {context} What would you say?",
                "Exploring a thought: {question} {context} What's your take?",
                "Open question: {question} {context} How do you navigate this?",
                "Seeking perspectives: {question} {context} What's worked for you?",
                "Collective wisdom time: {question} {context} What would you suggest?",
                "Honest curiosity: {question} {context} What's your story?"
            ],
            "observation": [
                "Noticed something interesting: {observation}. {context} Anyone else see this trend?",
                "Random observation: {observation}. {context} What patterns do you notice?",
                "Something caught my attention: {observation}. {context} Worth discussing?",
                "Interesting pattern: {observation}. {context} What's your take?",
                "Daily observation: {observation}. {context} Do you see this too?",
                "Quick note: {observation}. {context} What are your thoughts?",
                "Observation of the day: {observation}. {context} Sound about right?",
                "Something worth noting: {observation}. {context} What do you think?",
                "Pattern recognition: {observation}. {context} Match your experience?",
                "Real-world observation: {observation}. {context} What's your view?",
                "Trend spotting: {observation}. {context} Seeing this elsewhere?",
                "Cultural shift noted: {observation}. {context} What's driving this?",
                "Behavior pattern: {observation}. {context} What's behind this trend?",
                "Social observation: {observation}. {context} How does this land for you?",
                "Environmental notice: {observation}. {context} What changes do you see?"
            ],
            "tip_sharing": [
                "Small tip that helped me: {tip}. {context} What works for you?",
                "Something I learned: {tip}. {context} Any similar experiences?",
                "Quick share: {tip}. {context} What would you add?",
                "Practical discovery: {tip}. {context} Worth trying?",
                "Life hack I actually use: {tip}. {context} What's yours?",
                "Simple thing that works: {tip}. {context} What helps you?",
                "Lesson learned the hard way: {tip}. {context} Can you relate?",
                "Actually useful tip: {tip}. {context} What's worked for you?",
                "Real advice: {tip}. {context} What would you suggest?",
                "Something worth sharing: {tip}. {context} What's your approach?",
                "Game-changing insight: {tip}. {context} What's shifted things for you?",
                "Unexpected solution: {tip}. {context} What creative approaches do you use?",
                "Trial and error win: {tip}. {context} What have you discovered?",
                "Practical wisdom: {tip}. {context} What experience taught you most?",
                "Hard-earned knowledge: {tip}. {context} What would you tell others?"
            ],
            "trending_response": [
                "Seeing a lot about {trending_topic} lately. {insight} What's your take?",
                "Everyone's talking about {trending_topic}. {perspective} Thoughts?",
                "Noticed {trending_topic} trending. {angle} How do you see it?",
                "The {trending_topic} discussion is interesting. {viewpoint} What do you think?",
                "All the {trending_topic} content got me thinking: {reflection} Your perspective?",
                "Jumping on the {trending_topic} conversation: {thought} What's your view?",
                "About this whole {trending_topic} thing: {observation} Sound right?",
                "Adding to the {trending_topic} discussion: {insight} What would you say?",
                "My take on {trending_topic}: {opinion} What's yours?",
                "Since everyone's discussing {trending_topic}: {comment} Agree or disagree?",
                "The {trending_topic} trend has me curious: {wonder} What do you notice?",
                "Catching up on {trending_topic} discussions. {analysis} How are you processing this?",
                "Diving into the {trending_topic} conversation: {approach} What's your angle?",
                "Following the {trending_topic} thread: {connection} What connections do you see?",
                "Reflecting on all this {trending_topic} talk: {takeaway} What stands out to you?"
            ]
        }
    
    async def generate_dynamic_content(self, content_type: str = None) -> Dict:
        """Generate content based on audience distribution and trending topics"""
        try:
            # Get trending topics to influence content
            trending_topics = await self.trending_tracker.get_trending_topics(10)
            
            # Update trending adaptive topics
            if trending_topics:
                trending_words = [topic['topic'] for topic in trending_topics[:15]]
                self.content_categories['trending_adaptive']['topics'] = trending_words
            
            # Select category based on audience weights
            category = self._select_weighted_category()
            
            # Select specific topic
            topic = random.choice(self.content_categories[category]['topics'])
            
            # Check if we should make it trending-responsive
            use_trending = random.random() < 0.3  # 30% chance to reference trending
            
            if use_trending and trending_topics:
                return await self._generate_trending_content(topic, trending_topics)
            else:
                return await self._generate_standard_content(topic, category)
                
        except Exception as e:
            logger.error(f"❌ Error generating dynamic content: {e}")
            return self._generate_fallback_content()
    
    def _select_weighted_category(self) -> str:
        """Select category based on real audience distribution"""
        categories = list(self.content_categories.keys())
        weights = [self.content_categories[cat]['weight'] for cat in categories]
        return random.choices(categories, weights=weights)[0]
    
    async def _generate_trending_content(self, base_topic: str, trending_topics: List[Dict]) -> Dict:
        """Generate content that responds to trending topics"""
        trending_topic = random.choice(trending_topics)['topic']
        template = random.choice(self.dynamic_templates['trending_response'])
        
        # Generate contextual insight
        insights = [
            f"it connects to {base_topic} in interesting ways",
            f"it makes me think about {base_topic} differently",
            f"the {base_topic} angle is underexplored",
            f"there's a {base_topic} connection worth exploring",
            f"it relates to my thoughts on {base_topic}",
            f"it shifts perspective on {base_topic}",
            f"there's more to the {base_topic} side of this"
        ]
        
        insight = random.choice(insights)
        
        post_text = template.format(
            trending_topic=trending_topic,
            insight=insight,
            perspective=insight,
            angle=insight,
            viewpoint=insight,
            reflection=insight,
            thought=insight,
            observation=insight,
            opinion=insight,
            comment=insight,
            wonder=insight,
            analysis=insight,
            approach=insight,
            connection=insight,
            takeaway=insight
        )
        
        # Generate trending-aware hashtags
        trending_hashtags = await self.trending_tracker.get_trending_hashtags()
        base_hashtags = self._generate_topic_hashtags(base_topic)
        
        hashtags = (trending_hashtags[:2] + base_hashtags[:2])
        
        return {
            "post_text": post_text[:280],  # BlueSky limit
            "hashtags": " ".join(hashtags[:4]),
            "content_type": "trending_responsive",
            "base_topic": base_topic,
            "trending_element": trending_topic
        }
    
    async def _generate_standard_content(self, topic: str, category: str) -> Dict:
        """Generate standard content for a topic"""
        # Select appropriate template type
        template_types = {
            "lifestyle_wellness": ["personal_story", "tip_sharing", "question_starter"],
            "culture_society": ["observation", "question_starter", "personal_story"],
            "creativity_inspiration": ["personal_story", "tip_sharing", "observation"],
            "nature_environment": ["observation", "personal_story", "question_starter"],
            "tech_innovation": ["tip_sharing", "observation", "question_starter"],
            "professional_development": ["tip_sharing", "personal_story", "question_starter"],
            "creative_projects": ["personal_story", "tip_sharing", "observation"],
            "arts_culture": ["observation", "personal_story", "question_starter"]
        }
        
        available_types = template_types.get(category, ["personal_story", "question_starter"])
        template_type = random.choice(available_types)
        template = random.choice(self.dynamic_templates[template_type])
        
        # Generate content based on template type
        content_parts = self._generate_content_parts(topic, template_type)
        
        post_text = template.format(**content_parts)
        hashtags = self._generate_topic_hashtags(topic)
        
        return {
            "post_text": post_text[:280],
            "hashtags": " ".join(hashtags[:4]),
            "content_type": template_type,
            "category": category,
            "topic": topic
        }
    
    def _generate_content_parts(self, topic: str, template_type: str) -> Dict:
        """Generate appropriate content parts for templates"""
        parts = {}
        
        if template_type == "personal_story":
            insights = [
                f"how important {topic} really is",
                f"{topic} affects more than we realize",
                f"the subtle impact of {topic}",
                f"why {topic} deserves more attention",
                f"how {topic} shapes daily life"
            ]
            contexts = [
                f"Been exploring {topic} lately and it's eye-opening.",
                f"The more I learn about {topic}, the more fascinating it becomes.",
                f"My perspective on {topic} has shifted recently.",
                f"There's so much depth to {topic} that we often miss.",
                f"Real-world experience with {topic} is quite different from theory."
            ]
            parts.update({
                "insight": random.choice(insights),
                "context": random.choice(contexts)
            })
            
        elif template_type == "question_starter":
            questions = [
                f"how do you approach {topic}?",
                f"what role does {topic} play in your life?",
                f"how has {topic} evolved for you?",
                f"what surprises you most about {topic}?",
                f"how do you balance {topic} with other priorities?"
            ]
            contexts = [
                f"Trying to get better at {topic} myself.",
                f"Always learning new things about {topic}.",
                f"Curious about different approaches to {topic}.",
                f"Finding {topic} more complex than expected.",
                f"Exploring the nuances of {topic}."
            ]
            parts.update({
                "question": random.choice(questions),
                "context": random.choice(contexts)
            })
            
        elif template_type == "observation":
            observations = [
                f"more people are paying attention to {topic}",
                f"{topic} is becoming more mainstream",
                f"the conversation around {topic} is shifting",
                f"there's growing awareness about {topic}",
                f"new perspectives on {topic} are emerging"
            ]
            contexts = [
                f"It's becoming a bigger part of daily conversations.",
                f"Seeing it discussed in unexpected places.",
                f"The depth of understanding is increasing.",
                f"More nuanced views are developing.",
                f"Different communities are approaching it uniquely."
            ]
            parts.update({
                "observation": random.choice(observations),
                "context": random.choice(contexts)
            })
            
        elif template_type == "tip_sharing":
            tips = [
                f"taking small steps with {topic} beats overwhelming yourself",
                f"consistency with {topic} matters more than perfection",
                f"finding your own rhythm with {topic} is key",
                f"starting simple with {topic} builds confidence",
                f"connecting {topic} to existing habits makes it stick"
            ]
            contexts = [
                f"Consistency with {topic} makes a real difference.",
                f"Small changes in {topic} add up over time.",
                f"Personal experience taught me this about {topic}.",
                f"Trial and error with {topic} led to this insight.",
                f"What works for me with {topic} might help others."
            ]
            parts.update({
                "tip": random.choice(tips),
                "context": random.choice(contexts)
            })
        
        return parts
    
    def _generate_topic_hashtags(self, topic: str) -> List[str]:
        """Generate relevant hashtags for a topic"""
        # Extract key words from topic
        words = re.findall(r'\b\w+\b', topic.lower())
        key_words = [word for word in words if len(word) > 3 and word not in ['that', 'with', 'from', 'they', 'this', 'your', 'have', 'been', 'were', 'will']]
        
        # Generate hashtags
        hashtags = []
        
        # Direct topic hashtags (first 2 key words)
        for word in key_words[:2]:
            hashtags.append(f"#{word}")
        
        # Category-based hashtags
        category_tags = {
            "lifestyle": ["#wellness", "#mindful", "#growth", "#balance"],
            "wellness": ["#health", "#selfcare", "#mindfulness", "#wellbeing"],
            "culture": ["#society", "#thoughts", "#perspective", "#community"],
            "creativity": ["#creative", "#inspiration", "#art", "#imagination"],
            "creative": ["#design", "#artistic", "#innovation", "#expression"],
            "nature": ["#nature", "#sustainable", "#environment", "#outdoors"],
            "environment": ["#green", "#sustainability", "#earth", "#climate"],
            "tech": ["#technology", "#innovation", "#digital", "#future"],
            "technology": ["#tech", "#digital", "#innovation", "#tools"],
            "professional": ["#career", "#skills", "#development", "#work"],
            "career": ["#professional", "#growth", "#leadership", "#success"],
            "work": ["#productivity", "#career", "#skills", "#remote"],
            "project": ["#creative", "#building", "#learning", "#progress"],
            "art": ["#artistic", "#creative", "#culture", "#expression"],
            "music": ["#audio", "#sound", "#rhythm", "#melody"],
            "book": ["#reading", "#literature", "#learning", "#wisdom"],
            "travel": ["#adventure", "#culture", "#exploration", "#journey"],
            "food": ["#cooking", "#culture", "#health", "#community"],
            "relationship": ["#connection", "#human", "#community", "#love"],
            "learning": ["#education", "#growth", "#knowledge", "#skill"],
            "photography": ["#visual", "#art", "#moment", "#perspective"],
            "writing": ["#words", "#story", "#expression", "#thought"],
            "garden": ["#nature", "#growth", "#sustainable", "#peaceful"],
            "morning": ["#routine", "#wellness", "#productivity", "#mindful"],
            "stress": ["#wellness", "#mental", "#balance", "#selfcare"],
            "change": ["#growth", "#adaptation", "#resilience", "#life"],
            "habit": ["#productivity", "#wellness", "#growth", "#routine"],
            "time": ["#productivity", "#balance", "#life", "#mindful"],
            "space": ["#design", "#peaceful", "#organization", "#wellness"],
            "community": ["#connection", "#society", "#together", "#support"],
            "communication": ["#connection", "#relationship", "#skills", "#human"],
            "mindfulness": ["#wellness", "#present", "#awareness", "#peace"],
            "productivity": ["#efficiency", "#work", "#balance", "#growth"],
            "innovation": ["#technology", "#future", "#creative", "#progress"],
            "collaboration": ["#teamwork", "#community", "#connection", "#growth"],
            "leadership": ["#professional", "#growth", "#influence", "#development"],
            "design": ["#creative", "#visual", "#innovation", "#aesthetic"],
            "development": ["#growth", "#learning", "#progress", "#skills"]
        }
        
        # Add category-appropriate tags based on topic content
        for category, tags in category_tags.items():
            if category in topic.lower():
                hashtags.extend(random.sample(tags, min(2, len(tags))))
                break
        
        # If no category match, add general engagement tags
        if len(hashtags) < 3:
            general_tags = ["#discussion", "#thoughts", "#community", "#sharing", "#question", "#life", "#growth", "#learning"]
            hashtags.extend(random.sample(general_tags, min(2, len(general_tags))))
        
        return hashtags[:5]
    
    def _generate_fallback_content(self) -> Dict:
        """Generate safe fallback content"""
        fallbacks = [
            {
                "post_text": "What's one small thing that made your day better? Sometimes it's the little moments that count most. 🌟",
                "hashtags": "#thoughts #gratitude #moments #community",
                "content_type": "fallback"
            },
            {
                "post_text": "Quick question: what's something you learned recently that surprised you? Always curious about those 'aha' moments! 💡",
                "hashtags": "#learning #curiosity #growth #question",
                "content_type": "fallback"
            },
            {
                "post_text": "Anyone else find that the best conversations happen in the most unexpected places? Human connection is fascinating. 🤝",
                "hashtags": "#connection #conversation #human #thoughts",
                "content_type": "fallback"
            },
            {
                "post_text": "Observation: we're all figuring it out as we go, and that's perfectly okay. What's something you're still learning? 🌱",
                "hashtags": "#growth #learning #life #community",
                "content_type": "fallback"
            },
            {
                "post_text": "Random thought: the things that challenge us most often teach us the most. What's been your biggest teacher lately? 📚",
                "hashtags": "#wisdom #growth #challenges #learning",
                "content_type": "fallback"
            }
        ]
        
        return random.choice(fallbacks)

# Export for integration
__all__ = ['BlueSkyTrendingTracker', 'DynamicContentGenerator'] 