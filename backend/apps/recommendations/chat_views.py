import json
import os
import uuid
from datetime import datetime
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.db import models
from django.http import StreamingHttpResponse
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from common.response import ApiResponseMixin, ok, fail

from .chat_models import ChatMessage
from .engine import build_user_profile, recommend_artworks_hybrid


class ChatViewSet(ApiResponseMixin, GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_ai_client(self):
        api_key = os.getenv("AI_API_KEY")
        base_url = os.getenv("AI_API_BASE", "https://api.deepseek.com/v1")
        model = os.getenv("AI_MODEL", "deepseek-chat")
        
        return {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        }

    def _build_system_prompt(self, user):
        build_user_profile(user)
        
        from .models import UserProfile
        from apps.artworks.models import Artwork
        
        profile, _ = UserProfile.objects.get_or_create(user=user)
        
        preferences_info = "用户尚未设置偏好。"
        if profile.top_categories or profile.top_tags:
            categories = ", ".join(profile.top_categories[:5])
            tags = ", ".join(profile.top_tags[:5])
            preferences_info = f"用户偏好：分类[{categories}]，标签[{tags}]"

        recommendations = recommend_artworks_hybrid(user, limit=5)
        recommend_info = ""
        if recommendations:
            recommend_list = []
            for artwork, score in recommendations:
                recommend_list.append(f"{artwork.title} (匹配度:{score:.2f})")
            recommend_info = "\n推荐画作：\n" + "\n".join(recommend_list)

        all_artworks = Artwork.objects.filter(is_available=True).select_related('owner').order_by('-created_at')[:30]
        
        categories = {}
        for artwork in all_artworks:
            cat = artwork.category or '未分类'
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(artwork)
        
        artwork_info = "\n平台作品库（按分类分组）：\n"
        for cat, artworks_in_cat in categories.items():
            artwork_info += f"\n【{cat}】\n"
            for artwork in artworks_in_cat:
                tags_str = ", ".join(artwork.tags[:5]) if artwork.tags else ""
                artwork_info += f"- 《{artwork.title}》(ID:{artwork.id}) - 标签：{tags_str}，价格：{artwork.price}元\n"

        system_prompt = f"""你是星漫平台的AI助手，帮助用户发现喜欢的画作和画师。

平台信息：
- 星漫是一个动漫画廊/约稿平台
- 用户可以浏览、收藏、购买画作
- 用户可以发布委托需求

{preferences_info}
{recommend_info}

{artwork_info}

请遵循以下规则：
1. 用友好、活泼的语气与用户交流
2. 了解用户的喜好后，给出个性化推荐
3. 可以推荐画作、画师或委托类型
4. 当用户询问推荐时，优先基于用户画像推荐
5. 如果用户描述了具体需求，从平台作品库中匹配相关作品
6. 只能推荐平台作品库中存在的作品，绝对不能编造不存在的作品
7. 回答要简洁明了，避免冗长
8. **非常重要**：严格按照作品实际所属分类进行推荐，不得混淆不同分类的作品！例如：芙宁娜属于"原神"分类，诺姆属于"绝区零"分类，绝对不能说芙宁娜是绝区零的作品！

回复格式要求：
- 可以使用Markdown格式
- 推荐画作时，必须在作品名后附加作品标记，格式为《作品名》[作品:ID]，例如：《诺姆》[作品:1]
- 作品标记非常重要，必须正确使用，这样用户才能直接看到作品图片
- 保持对话自然流畅"""

        return system_prompt

    def _get_conversation_history(self, user, conversation_id=None, limit=10):
        if conversation_id:
            messages = ChatMessage.objects.filter(user=user, conversation_id=conversation_id).order_by("created_at")[:limit]
        else:
            messages = ChatMessage.objects.filter(user=user).order_by("-created_at")[:limit]
            messages = list(messages)[::-1]
        
        history = []
        for msg in messages:
            history.append({
                "role": "user" if msg.is_user else "assistant",
                "content": msg.message,
            })
        return history

    def _call_ai_stream(self, system_prompt, messages):
        client = self._get_ai_client()
        
        if not client["api_key"]:
            return self._get_mock_stream_response(messages)

        payload = {
            "model": client["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages
            ],
            "temperature": 0.7,
            "max_tokens": 2048,
            "stream": True,
        }

        headers = {
            "Authorization": f"Bearer {client['api_key']}",
            "Content-Type": "application/json",
        }

        try:
            full_url = client["base_url"].rstrip("/") + "/chat/completions"
            response = requests.post(
                full_url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=120,
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith('data: '):
                        data = line_str[6:]
                        if data == '[DONE]':
                            break
                        try:
                            json_data = json.loads(data)
                            if json_data.get('choices'):
                                content = json_data['choices'][0]['delta'].get('content', '')
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
            
        except requests.exceptions.RequestException as e:
            yield f"错误：{str(e)}"

    def _get_mock_stream_response(self, messages):
        last_message = messages[-1]["content"] if messages else ""
        
        responses = {
            "你好": "你好呀！我是星漫 AI 助手，很高兴为你服务！😊 我可以帮你发现喜欢的画作和画师，有什么想聊的吗？",
            "推荐": "好的！根据你的浏览记录，我为你推荐以下画作：\n\n1. 《樱花树下》- 二次元风格，匹配度 0.85\n2. 《古风美人》- 古风风格，匹配度 0.78\n3. 《赛博朋克》- 科幻风格，匹配度 0.72\n\n如果需要更具体的推荐，请告诉我你的喜好~",
            "画师": "星漫平台有很多优秀的画师！比如：\n\n- 画师A：擅长二次元插画，画风清新可爱\n- 画师B：专注古风创作，线条细腻\n- 画师C：擅长科幻题材，色彩丰富\n\n你对哪种风格比较感兴趣呢？",
            "头像": "定制头像服务很受欢迎呢！你可以告诉我想要的风格（二次元、古风、写实等）和主题，我来帮你推荐合适的画师~",
            "二次元": "二次元风格是我们平台最受欢迎的！推荐一些热门作品：\n\n🌸 《初音未来同人》\n🎮 《游戏角色原画》\n✨ 《少女插画合集》\n\n需要了解更多可以告诉我哦~",
            "古风": "古风画作韵味十足！推荐作品：\n\n🏮 《汉服美人图》\n🍃 《水墨山水》\n🎋 《竹林深处》\n\n这些都是很受欢迎的古风作品~",
        }
        
        response_text = responses.get(last_message)
        if not response_text:
            response_text = f"我收到了你的消息：「{last_message}」\n\n这是一个模拟回复。要体验完整的 AI 对话功能，请配置 AI_API_KEY 环境变量。"
        
        for char in response_text:
            yield char
            import time
            time.sleep(0.02)

    @action(detail=False, methods=["post"], url_path="send")
    def send_message(self, request):
        message = request.data.get("content", "").strip()
        conversation_id = request.data.get("conversation_id")
        
        if not message:
            return fail("请输入消息内容")

        if not conversation_id:
            conversation_id = str(uuid.uuid4())

        ChatMessage.objects.create(
            user=request.user,
            message=message,
            is_user=True,
            conversation_id=conversation_id,
        )

        system_prompt = self._build_system_prompt(request.user)
        history = self._get_conversation_history(request.user, conversation_id)

        result = self._call_ai(system_prompt, history)

        if result.get("success"):
            ai_message = ChatMessage.objects.create(
                user=request.user,
                message=result["content"],
                is_user=False,
                conversation_id=conversation_id,
            )

            return ok({
                "conversation_id": conversation_id,
                "content": ai_message.message,
                "timestamp": ai_message.created_at.isoformat(),
            })
        else:
            return fail(result.get("error", "AI服务调用失败"), code=500)

    @action(detail=False, methods=["post"], url_path="stream")
    def send_message_stream(self, request):
        message = request.data.get("content", "").strip()
        conversation_id = request.data.get("conversation_id")
        
        if not message:
            return fail("请输入消息内容")

        if not conversation_id:
            conversation_id = str(uuid.uuid4())

        ChatMessage.objects.create(
            user=request.user,
            message=message,
            is_user=True,
            conversation_id=conversation_id,
        )

        system_prompt = self._build_system_prompt(request.user)
        history = self._get_conversation_history(request.user, conversation_id)

        hybrid_recommendations = recommend_artworks_hybrid(request.user, limit=6)

        full_content = []
        
        def generate():
            nonlocal full_content
            for chunk in self._call_ai_stream(system_prompt, history):
                full_content.append(chunk)
                yield f"data: {json.dumps({'content': chunk, 'conversation_id': conversation_id})}\n\n"
            
            if full_content:
                ai_message = ChatMessage.objects.create(
                    user=request.user,
                    message=''.join(full_content),
                    is_user=False,
                    conversation_id=conversation_id,
                )
                
                matched_artworks = self._match_artworks_by_keyword(
                    message, ''.join(full_content), 
                    fallback_recommendations=hybrid_recommendations
                )
                yield f"data: {json.dumps({'content': '', 'conversation_id': conversation_id, 'done': True, 'message_id': ai_message.id, 'artworks': matched_artworks})}\n\n"
        
        return StreamingHttpResponse(
            generate(),
            content_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            }
        )
    
    def _match_artworks_by_keyword(self, user_message, ai_response, fallback_recommendations=None):
        from apps.artworks.models import Artwork
        all_artworks = Artwork.objects.filter(is_available=True)
        
        matched = []
        categories = {}
        for artwork in all_artworks:
            cat = artwork.category or '未分类'
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(artwork)
        
        keywords = user_message + ' ' + ai_response
        
        for cat, artworks_in_cat in categories.items():
            if cat in keywords:
                for artwork in artworks_in_cat:
                    image_url = str(artwork.image) if artwork.image else ''
                    if image_url and not image_url.startswith('http'):
                        image_url = 'http://127.0.0.1:8000/media/' + image_url.lstrip('/')
                    
                    matched.append({
                        'id': artwork.id,
                        'title': artwork.title,
                        'image_url': image_url,
                        'price': str(artwork.price),
                        'category': artwork.category,
                    })
        
        for artwork in all_artworks:
            if artwork.title and artwork.title in keywords:
                already_matched = any(m['id'] == artwork.id for m in matched)
                if not already_matched:
                    image_url = str(artwork.image) if artwork.image else ''
                    if image_url and not image_url.startswith('http'):
                        image_url = 'http://127.0.0.1:8000/media/' + image_url.lstrip('/')
                    
                    matched.append({
                        'id': artwork.id,
                        'title': artwork.title,
                        'image_url': image_url,
                        'price': str(artwork.price),
                        'category': artwork.category,
                    })
        
        if not matched and fallback_recommendations:
            for artwork, score in fallback_recommendations[:6]:
                image_url = str(artwork.image) if artwork.image else ''
                if image_url and not image_url.startswith('http'):
                    image_url = 'http://127.0.0.1:8000/media/' + image_url.lstrip('/')
                
                matched.append({
                    'id': artwork.id,
                    'title': artwork.title,
                    'image_url': image_url,
                    'price': str(artwork.price),
                    'category': artwork.category,
                    'match_score': round(score, 2),
                })
        
        return matched

    def _call_ai(self, system_prompt, messages):
        client = self._get_ai_client()
        
        if not client["api_key"]:
            return self._get_mock_response(messages)

        payload = {
            "model": client["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages
            ],
            "temperature": 0.7,
            "max_tokens": 2048,
        }

        headers = {
            "Authorization": f"Bearer {client['api_key']}",
            "Content-Type": "application/json",
        }

        try:
            full_url = client["base_url"].rstrip("/") + "/chat/completions"
            response = requests.post(
                full_url,
                json=payload,
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            
            if "choices" in data and data["choices"]:
                return {
                    "success": True,
                    "content": data["choices"][0]["message"]["content"],
                }
            return {"success": False, "error": "No response from AI"}
            
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def _get_mock_response(self, messages):
        last_message = messages[-1]["content"] if messages else ""
        
        responses = {
            "你好": "你好呀！我是星漫 AI 助手，很高兴为你服务！😊 我可以帮你发现喜欢的画作和画师，有什么想聊的吗？",
            "推荐": "好的！根据你的浏览记录，我为你推荐以下画作：\n\n1. 《樱花树下》- 二次元风格，匹配度 0.85\n2. 《古风美人》- 古风风格，匹配度 0.78\n3. 《赛博朋克》- 科幻风格，匹配度 0.72\n\n如果需要更具体的推荐，请告诉我你的喜好~",
            "画师": "星漫平台有很多优秀的画师！比如：\n\n- 画师A：擅长二次元插画，画风清新可爱\n- 画师B：专注古风创作，线条细腻\n- 画师C：擅长科幻题材，色彩丰富\n\n你对哪种风格比较感兴趣呢？",
            "头像": "定制头像服务很受欢迎呢！你可以告诉我想要的风格（二次元、古风、写实等）和主题，我来帮你推荐合适的画师~",
            "二次元": "二次元风格是我们平台最受欢迎的！推荐一些热门作品：\n\n🌸 《初音未来同人》\n🎮 《游戏角色原画》\n✨ 《少女插画合集》\n\n需要了解更多可以告诉我哦~",
            "古风": "古风画作韵味十足！推荐作品：\n\n🏮 《汉服美人图》\n🍃 《水墨山水》\n🎋 《竹林深处》\n\n这些都是很受欢迎的古风作品~",
        }
        
        for key, response in responses.items():
            if key in last_message:
                return {"success": True, "content": response}
        
        return {
            "success": True,
            "content": f"我收到了你的消息：「{last_message}」\n\n这是一个模拟回复。要体验完整的 AI 对话功能，请配置 AI_API_KEY 环境变量。\n\n你可以问我关于画作推荐、画师介绍、委托定制等问题哦！"
        }

    @action(detail=False, methods=["get"], url_path="history")
    def get_history(self, request):
        conversation_id = request.query_params.get("conversation_id")
        limit = int(request.query_params.get("limit", 50))

        if conversation_id:
            messages = ChatMessage.objects.filter(
                user=request.user,
                conversation_id=conversation_id
            ).order_by("created_at")[:limit]
        else:
            messages = ChatMessage.objects.filter(
                user=request.user
            ).order_by("-created_at")[:limit]

        return ok({
            "messages": [{
                "role": "user" if msg.is_user else "assistant",
                "content": msg.message,
                "created_at": msg.created_at.isoformat(),
            } for msg in messages]
        })

    @action(detail=False, methods=["post"], url_path="new")
    def new_conversation(self, request):
        conversation_id = str(uuid.uuid4())
        return ok({"conversation_id": conversation_id})

    @action(detail=False, methods=["post"], url_path="clear")
    def clear_history(self, request):
        conversation_id = request.query_params.get("conversation_id")
        if conversation_id:
            ChatMessage.objects.filter(user=request.user, conversation_id=conversation_id).delete()
        else:
            ChatMessage.objects.filter(user=request.user).delete()
        return ok(None, message="聊天记录已清空")

    @action(detail=False, methods=["get"], url_path="conversations")
    def list_conversations(self, request):
        conversations = ChatMessage.objects.filter(user=request.user)\
            .values("conversation_id")\
            .annotate(last_time=models.Max("created_at"))\
            .order_by("-last_time")[:10]

        result = []
        for conv in conversations:
            last_msg = ChatMessage.objects.filter(
                user=request.user,
                conversation_id=conv["conversation_id"]
            ).order_by("-created_at").first()
            
            first_user_msg = ChatMessage.objects.filter(
                user=request.user,
                conversation_id=conv["conversation_id"],
                is_user=True
            ).order_by("created_at").first()
            
            title = first_user_msg.message[:20] if first_user_msg else "新对话"

            result.append({
                "id": conv["conversation_id"],
                "title": title,
                "last_message": last_msg.message[:50] if last_msg else "",
                "updated_at": conv["last_time"].isoformat() if conv["last_time"] else "",
            })

        return ok({"conversations": result})