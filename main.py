import os
import requests

def test_connection():
    # 1. 讀取鑰匙
    token = os.environ.get("LINE_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    # 印出來檢查一下有沒有讀到 (只印前幾碼，確保安全)
    print(f"🔑 Token 檢查: {token[:10]}..." if token else "❌ 沒讀到 Token")
    print(f"👤 UserID 檢查: {user_id}" if user_id else "❌ 沒讀到 User ID")
    
    if not token or not user_id:
        print("⛔ 測試終止：請先去 Secrets 設定好鑰匙")
        return

    # 2. 發送測試訊息
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": "🎉 恭喜！連線測試成功！你的設定是完全正確的！"
            }
        ]
    }
    
    print("🚀 正在發送測試訊號...")
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        # 3. 顯示結果 (這就是重點！)
        print(f"📡 HTTP 狀態碼: {response.status_code}")
        print(f"📝 回應內容: {response.text}")
        
        if response.status_code == 200:
            print("✅ 成功！快看手機！")
        else:
            print("❌ 失敗！請截圖這個畫面給我看")
            
    except Exception as e:
        print(f"💥 發生錯誤: {e}")

if __name__ == "__main__":
    test_connection()
