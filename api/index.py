# api/index.py
import os
from fastapi import FastAPI, HTTPException, Security
from fastapi.security.api_key import APIKeyQuery
from fastapi.responses import PlainTextResponse
from pathlib import Path
import sys, os
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.fetcher import ScoreFetcher
from utils import database

app = FastAPI()

api_key_query = APIKeyQuery(name="secret", auto_error=False)

def get_api_key(api_key: str = Security(api_key_query)):
    expected_api_key = os.environ.get("API_SECRET_TOKEN")
    if not expected_api_key:
        raise HTTPException(status_code=500, detail="服务器未配置API密钥")
    if api_key == expected_api_key:
        return api_key
    else:
        raise HTTPException(status_code=403, detail="提供的密钥无效或缺失")

@app.get("/api/fetch-scores") 
@app.post("/api/fetch-scores")
async def trigger_fetch_scores(api_key: str = Security(get_api_key)):
    username = os.environ.get("SWJTU_USERNAME")
    password = os.environ.get("SWJTU_PASSWORD")

    if not username or not password:
        raise HTTPException(status_code=500, detail="服务器未配置学号或密码环境变量")

    print("--- 任务开始: 准备获取成绩 ---")
    fetcher = ScoreFetcher(username=username, password=password)

    try:
        # 1. 登录
        login_success = fetcher.login()
        if not login_success:
            return {"status": "error", "message": "登录失败，请检查Vercel日志。"}

        # 2. 获取并合并总成绩和平时成绩
        combined_scores = fetcher.get_combined_scores()

        if not combined_scores:
            return {"status": "error", "message": "未能获取到任何成绩数据。"}

        # 3. 将合并后的成绩数据存入
        print("正在将成绩数据存入数据库...")
        old = database.get_latest_scores()
        upsert_results = database.save_scores(combined_scores)
        # save_scores() 吞掉异常并返回 None，不检查就会把写入失败报成成功。
        if upsert_results is None:
            raise HTTPException(status_code=500, detail="成绩保存失败，本次结果未写入历史。")
        new = database.get_latest_scores()
        print("--- 任务完成 ---")
        return {
            "status": "success",
            "message": "成绩获取和存储任务已完成。",
            "summary": {
                "total_records_processed": len(combined_scores),
                "old_records_count": len(old) if old else 0,
                "new_records_count": len(new) if new else 0,
            }
        }

    except Exception as e:
        print(f"执行任务时发生严重错误: {e}")
        raise HTTPException(status_code=500, detail=f"执行爬虫任务时发生内部错误: {str(e)}")

@app.get("/")
def read_root():
    return {"status": "online", "message": "SWJTU Score Fetcher API is running with upstash."}

@app.get("/api/check-login-usability") 
@app.post("/api/check-login-usability")
async def trigger_check_login_usability(api_key: str = Security(get_api_key)):
    """检查当前配置的学号和密码是否能成功登录教务系统"""
    username = os.environ.get("SWJTU_USERNAME")
    password = os.environ.get("SWJTU_PASSWORD")
    if not username or not password:
        raise HTTPException(status_code=500, detail="服务器未配置学号或密码环境变量")
    try:
        fetcher = ScoreFetcher(username=username, password=password)
        login_success = fetcher.login()
    except Exception as e:
        print(f"检查登录有效性时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"检查登录有效性时发生内部错误: {str(e)}")
    if login_success:
        return {"status": "success", "message": "登录成功，学号和密码有效。"}
    else:
        raise HTTPException(status_code=500, detail=f"登录失败，请检查学号和密码是否正确；或为教务处服务器外网访问被关闭。")
    
@app.get("/api/monitor-scores")
@app.post("/api/monitor-scores")
async def trigger_monitor_scores(api_key: str = Security(get_api_key)):
    """监控成绩变化，如有变动则发送邮件通知"""
    from utils.notify import send_email
    
    username = os.environ.get("SWJTU_USERNAME")
    password = os.environ.get("SWJTU_PASSWORD")
    
    # 邮件配置
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    notify_email = os.environ.get("NOTIFY_EMAIL")
    email_password = os.environ.get("EMAIL_PASSWORD")
    
    if not username or not password:
        raise HTTPException(status_code=500, detail="服务器未配置学号或密码环境变量")
    
    if not smtp_host or not notify_email or not email_password:
        raise HTTPException(status_code=500, detail="服务器未配置邮件环境变量")
    
    print("--- 任务开始: 监控成绩变化 ---")
    
    try:
        # 1. 获取数据库中的旧成绩
        print("正在从数据库获取历史成绩...")
        old_scores = database.get_latest_scores()

        # get_latest_scores() 用 None 表示读取失败、[] 表示确实没有历史成绩。
        # 两者必须区分：把读取失败当成没有历史，会把整份成绩单误判为
        # “全部新增”并群发通知。
        if old_scores is None:
            return {"status": "error", "message": "历史成绩读取失败，本次跳过对比以避免误报新增。"}
        
        # 2. 登录并获取最新成绩
        print("正在登录教务系统获取最新成绩...")
        fetcher = ScoreFetcher(username=username, password=password)
        login_success = fetcher.login()
        
        if not login_success:
            return {"status": "error", "message": "登录失败，请检查日志。"}
        
        new_scores = fetcher.get_combined_scores()
        
        if not new_scores:
            return {"status": "error", "message": "未能获取到任何成绩数据。"}
        
        # 3. 比较成绩变化
        print("正在比较成绩变化...")
        changes = []
        
        # 创建旧成绩的快速查找字典 (课程名称+教师) -> 成绩记录
        old_scores_map = {}
        if old_scores:
            for score in old_scores:
                key = (score.get('课程名称'), score.get('教师'))
                old_scores_map[key] = score
        
        # 检查新成绩中的变化
        for new_score in new_scores:
            key = (new_score.get('课程名称'), new_score.get('教师'))
            
            if key not in old_scores_map:
                # 课程不存在于旧数据中，检查新增的内容
                
                # 新增总成绩
                if new_score.get('成绩'):
                    changes.append({
                        'type': '新增总成绩',
                        'course': new_score
                    })
                
                # 新增平时成绩
                if new_score.get('平时成绩详情'):
                    changes.append({
                        'type': '新增平时成绩',
                        'course': new_score,
                        'new_details': new_score.get('平时成绩详情')
                    })
            else:
                # 课程存在，检查是否有变化
                old_score = old_scores_map[key]
                
                # 检查总成绩
                old_grade = old_score.get('成绩')
                new_grade = new_score.get('成绩')
                
                if old_grade != new_grade:
                    if not old_grade and new_grade:
                        # 之前没有总成绩，现在有了
                        changes.append({
                            'type': '新增总成绩',
                            'course': new_score
                        })
                    else:
                        # 总成绩发生变化
                        changes.append({
                            'type': '总成绩变化',
                            'course': new_score,
                            'old_value': old_grade,
                            'new_value': new_grade
                        })
                
                # 检查平时成绩详情
                old_details = old_score.get('平时成绩详情') or []
                new_details = new_score.get('平时成绩详情') or []
                
                if old_details != new_details:
                    if not old_details and new_details:
                        # 之前没有平时成绩，现在有了
                        changes.append({
                            'type': '新增平时成绩',
                            'course': new_score,
                            'new_details': new_details
                        })
                    else:
                        # 平时成绩发生变化
                        changes.append({
                            'type': '平时成绩变化',
                            'course': new_score,
                            'old_details': old_details,
                            'new_details': new_details
                        })
        
        # 4. 如果有变化，发送邮件
        if changes:
            print(f"检测到 {len(changes)} 项成绩变化，正在发送邮件通知...")
            
            # 生成 HTML 表格
            html_body = generate_change_notification_html(changes)
            
            # 发送邮件
            send_email(
                smtp_server=smtp_host,
                smtp_port=smtp_port,
                sender_email=notify_email,
                sender_password=email_password,
                receiver_email=notify_email,
                subject="🎓 成绩更新通知",
                body=html_body
            )
            
            # 保存新成绩到数据库
            print("正在将新成绩保存到数据库...")
            # 通知已经发出，若此时保存失败，下一轮会以同样的历史做对比，
            # 把这批变化原样再报一次，必须显式失败。
            if database.save_scores(new_scores) is None:
                return {
                    "status": "error",
                    "message": f"已发送 {len(changes)} 项变化通知，但历史成绩保存失败；"
                               f"下次运行会重复报告同样的变化，请检查 GIST_PAT 与网络。",
                    "changes_count": len(changes),
                }
            
            return {
                "status": "success",
                "message": f"检测到 {len(changes)} 项成绩变化，已发送邮件通知。",
                "changes_count": len(changes)
            }
        else:
            print("未检测到成绩变化。")
            return {
                "status": "success",
                "message": "成绩无变化。",
                "changes": []
            }
    
    except Exception as e:
        print(f"监控成绩时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"监控成绩时发生内部错误: {str(e)}")
    
    finally:
        print("--- 任务完成 ---")

def generate_change_notification_html(changes):
    """生成成绩变化通知的 HTML 表格"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            h2 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
            .change-section { margin: 20px 0; padding: 15px; background-color: #f8f9fa; border-radius: 5px; }
            .change-type { font-weight: bold; color: #e74c3c; margin-bottom: 10px; }
            table { border-collapse: collapse; width: 100%; margin: 10px 0; background-color: white; }
            th { background-color: #3498db; color: white; padding: 12px; text-align: left; }
            td { border: 1px solid #ddd; padding: 10px; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            .new-value { color: #3498db; font-weight: bold; }
            .old-value { color: #95a5a6; text-decoration: line-through; }
            .highlight { background-color: #fff3cd; }
        </style>
    </head>
    <body>
        <h2>🎓 成绩更新通知</h2>
        <p>检测到您的成绩有以下变化：</p>
    """
    
    for change in changes:
        course = change['course']
        change_type = change['type']
        
        html += f'<div class="change-section">'
        html += f'<div class="change-type">【{change_type}】{course.get("课程名称", "未知课程")} - {course.get("教师", "")}</div>'
        
        if change_type == '新增总成绩':
            html += '<table>'
            html += '<tr><th>项目</th><th>内容</th></tr>'
            html += f'<tr><td>课程名称</td><td>{course.get("课程名称", "")}</td></tr>'
            html += f'<tr><td>教师</td><td>{course.get("教师", "")}</td></tr>'
            html += f'<tr><td>成绩</td><td class="new-value">{course.get("成绩", "")}</td></tr>'
            html += f'<tr><td>学分</td><td>{course.get("学分", "")}</td></tr>'
            html += f'<tr><td>期末</td><td>{course.get("期末", "")}</td></tr>'
            html += f'<tr><td>平时</td><td>{course.get("平时", "")}</td></tr>'
            html += '</table>'
            
        elif change_type == '总成绩变化':
            html += '<table>'
            html += '<tr><th>项目</th><th>原成绩</th><th>新成绩</th></tr>'
            html += f'<tr class="highlight"><td>成绩</td><td class="old-value">{change.get("old_value", "")}</td><td class="new-value">{change.get("new_value", "")}</td></tr>'
            html += '</table>'
        
        elif change_type == '新增平时成绩':
            new_details = change.get('new_details', [])
            if new_details:
                html += '<table>'
                html += '<tr><th>平时成绩名称</th><th>成绩</th><th>占比</th><th>提交时间</th></tr>'
                for detail in new_details:
                    html += '<tr>'
                    html += f'<td>{detail.get("平时成绩名称", "")}</td>'
                    html += f'<td class="new-value">{detail.get("成绩", "")}</td>'
                    html += f'<td>{detail.get("占比", "")}</td>'
                    html += f'<td>{detail.get("提交时间", "")}</td>'
                    html += '</tr>'
                html += '</table>'
            
        elif change_type == '平时成绩变化':
            html += '<p><strong>平时成绩详情有变化：</strong></p>'
            
            new_details = change.get('new_details', [])
            if new_details:
                html += '<table>'
                html += '<tr><th>平时成绩名称</th><th>成绩</th><th>占比</th><th>提交时间</th></tr>'
                for detail in new_details:
                    html += '<tr>'
                    html += f'<td>{detail.get("平时成绩名称", "")}</td>'
                    html += f'<td class="new-value">{detail.get("成绩", "")}</td>'
                    html += f'<td>{detail.get("占比", "")}</td>'
                    html += f'<td>{detail.get("提交时间", "")}</td>'
                    html += '</tr>'
                html += '</table>'
        
        html += '</div>'
    
    html += """
        <p style="margin-top: 30px; color: #7f8c8d;">
            <em>此邮件由成绩监控系统自动发送，请勿回复。</em><br>
            <em>请登录教务系统查看完整信息。</em>
        </p>
    </body>
    </html>
    """
    
    return html

if __name__ == "__main__":
    sf = ScoreFetcher(os.environ.get("SWJTU_USERNAME"), os.environ.get("SWJTU_PASSWORD"))  # 仅用于本地测试
    sf.login()
    sc = sf.get_combined_scores()  # 仅用于本地测试
    print(f"获取到 {len(sc) if sc else 0} 条成绩记录")