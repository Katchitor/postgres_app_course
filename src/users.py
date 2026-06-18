from dataclasses import dataclass
from db import get_conn

@dataclass
class User:
    id: int
    username: str
    role: str


def find_user_by_login_and_pass(username: str, password: str) -> User | None:
    """Находит пользователя по логину и проверяет пароль"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, username, role 
            FROM auth.users 
            WHERE username = %s AND password = crypt(%s, password)
        """, (username, password))
        result = cur.fetchone()
        if result:
            return User(id=result[0], username=result[1], role=result[2])
        return None


def get_user(user_id: int) -> User | None:
    """Возвращает пользователя по ID"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, username, role FROM auth.users WHERE id = %s", (user_id,))
        result = cur.fetchone()
        if result:
            return User(id=result[0], username=result[1], role=result[2])
        return None