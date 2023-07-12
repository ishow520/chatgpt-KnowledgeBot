import datetime
import time

import requests
from common.log import logger
from bridge.context import Context
from bridge.reply import Reply, ReplyType
from bot.bot import Bot
from bot.chatgpt.chat_gpt_session import ChatGPTSession
from bot.session_manager import SessionManager
from config import conf


class DifyAiBot(Bot):
    AUTH_FAILED_CODE = 401

    def __init__(self):
        self.base_url = conf().get("base_url") or "https://api.gojiberrys.cn/api/openapi"
        self.sessions = SessionManager(ChatGPTSession, model=conf().get("model") or "gpt-3.5-turbo")
        self.reply_counts = {}
        self.last_update_date = datetime.date.today()
        self.max_daily_replies = conf().get("max_daily_replies", 10)
        self.max_single_chat_replies = conf().get("max_single_chat_replies")
        self.max_group_chat_replies = conf().get("max_group_chat_replies")
        self.ad_message = conf().get("ad_message")

    def __del__(self):
        print("del")

    def reply(self, query, context: Context = None) -> Reply:
        # Get the WeChat nickname from the context
        wechat_nickname = context.get("wechat_nickname")

        # Check if we've moved to a new day since the last update
        if datetime.date.today() != self.last_update_date:
            # If so, reset the reply counts and update the date
            self.reply_counts = {}
            self.last_update_date = datetime.date.today()

        # Check if the user has already reached the maximum number of replies for the day
        if self.reply_counts.get(wechat_nickname, 0) >= self.max_daily_replies:
            # If so, return an error message
            return Reply(ReplyType.ERROR, "已达到最大回复次数")

        # Otherwise, increment the user's reply count
        self.reply_counts[wechat_nickname] = self.reply_counts.get(wechat_nickname, 0) + 1

        # Continue processing the reply as before...
        reply = self._chat(query, context)

        return reply

    def _chat(self, query, context, retry_count=0):
        if retry_count >= 5:
            logger.warn("[dify] 失败超过最大重试次数")
            return Reply(ReplyType.ERROR, "请再问我一次吧")

        try:
            session_id = context.get("session_id")
            session = self.sessions.session_query(query, session_id)

            if session.messages and session.messages[0].get("role") == "system":
                session.messages.pop(0)

            dify_api_key = conf().get("dify_api_key")
            response_mode = conf().get("response_mode")
            user = conf().get("user")
            conversation_id = conf().get("conversation_id")

            prompts = []
            for msg in session.messages:
                if "role" in msg and "content" in msg:
                    prompt = {"obj": msg["role"], "value": msg["content"]}
                    prompts.append(prompt)
                else:
                    logger.warn(f"[dify] 无效的消息格式: {msg}")

            body = {
                "response_mode": response_mode,
                "user": user,
                "inputs":{},
                "query":query,
                "conversation_id":conversation_id
            }
            headers = {"Authorization": f"Bearer {dify_api_key}", "Content-Type": "application/json"}

            response = requests.post(url=f"{self.base_url}/chat-messages", json=body, headers=headers)

            logger.info(f"[dify] 响应状态码: {response.status_code}")
            logger.info(f"[dify] 响应内容: {response.content}")


            if response.status_code == 200:
                res = response.json()
                chat_reply = res.get("answer")
                conversation_id = res.get("conversation_id")

                # 在这里修改广告信息的处理部分
                ad_message = conf().get("ad_message")
                if isinstance(chat_reply, str) and ad_message:
                    ad_prefix = "[庆祝][庆祝][庆祝]"
                    ad_separator = "\n✨✨✨✨✨✨✨✨✨✨"
                    ad_message = f"\n{ad_separator}\n{ad_message}\n{ad_separator}"
                    styled_ad_prefix = f"**{ad_prefix}**"
                    chat_reply_with_ad = chat_reply + f"\n{styled_ad_prefix}{ad_message}"
                    return Reply(ReplyType.TEXT, chat_reply_with_ad)

                if isinstance(chat_reply, str):
                    return Reply(ReplyType.TEXT, chat_reply)

                # 添加以下两行代码来处理其他类型的回复
                elif isinstance(chat_reply, dict) and chat_reply.get("type") == "text":
                    reply_text = chat_reply.get("message")
                    return Reply(ReplyType.TEXT, reply_text)

                else:
                    logger.error(f"[dify] 回复类型不正确: {type(chat_reply)}")
                    return Reply(ReplyType.TEXT, str(chat_reply))

            else:
                time.sleep(2)
                logger.warn(f"[dify] 进行重试，次数={retry_count + 1}")
                return self._chat(query, context, retry_count + 1)

        except Exception as e:
            logger.error(f"[dify] 异常: {str(e)}")
            if 'response' in locals():
                logger.error(f"[dify] API响应内容: {response.content.decode('utf-8')}")

            # 发生错误时，检查配置文件是否存在广告信息，如果存在则返回广告信息作为错误提示
            ad_message = conf().get("ad_message")
            if ad_message:
                return Reply(ReplyType.ERROR, ad_message)

