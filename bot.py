# uia_vps_bot.py
"""
UIA HOST - Advanced VPS Management Bot
Created by REONDEV
Version: 3.0.0
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import subprocess
import json
from datetime import datetime, timedelta
import shlex
import logging
import shutil
import os
from typing import Optional, List, Dict, Any
import threading
import time
import sqlite3
import random
import re
import sys
from dataclasses import dataclass
from enum import Enum

# ============================================================
# CONFIGURATION
# ============================================================

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', '676790FuckMTUxNzIxMjMzNzk3Nzk1MDI0OQ.GWEdmz.rQNHFy93FqpRAABijn6auKPmynTBlqedzH0_is')
BOT_NAME = os.getenv('BOT_NAME', 'Aura Nodez')
PREFIX = os.getenv('PREFIX', '/')
YOUR_SERVER_IP = os.getenv('YOUR_SERVER_IP', '127.0.0.1')
MAIN_ADMIN_ID = int(os.getenv('MAIN_ADMIN_ID', '1018004252930605057'))
VPS_USER_ROLE_ID = int(os.getenv('VPS_USER_ROLE_ID', '0'))
DEFAULT_STORAGE_POOL = os.getenv('DEFAULT_STORAGE_POOL', 'default')
EMBED_COLOR = 0x0a0a1a
ACCENT_COLOR = 0x00d4ff
SUCCESS_COLOR = 0x00ff88
ERROR_COLOR = 0xff3366
WARNING_COLOR = 0xffaa00

# Branding
BRAND_LOGO = "https://ibb.co/pj7hj6mQ"
BRAND_FOOTER = "AURA NODEZ VPS Manager • Premium Virtual Private Servers"
BRAND_THUMBNAIL = "https://ibb.co/pj7hj6mQ"

# OS Options
OS_OPTIONS = [
    {"label": "🟣 Ubuntu 20.04 LTS", "value": "ubuntu:20.04", "emoji": "🐧"},
    {"label": "🟣 Ubuntu 22.04 LTS", "value": "ubuntu:22.04", "emoji": "🐧"},
    {"label": "🟣 Ubuntu 24.04 LTS", "value": "ubuntu:24.04", "emoji": "🐧"},
    {"label": "🔴 Debian 10 (Buster)", "value": "images:debian/10", "emoji": "📦"},
    {"label": "🔴 Debian 11 (Bullseye)", "value": "images:debian/11", "emoji": "📦"},
    {"label": "🔴 Debian 12 (Bookworm)", "value": "images:debian/12", "emoji": "📦"},
    {"label": "🔴 Debian 13 (Trixie)", "value": "images:debian/13", "emoji": "📦"},
]

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('uia_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('uia_vps_bot')

# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect('uia_vps.db')
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id TEXT PRIMARY KEY
    )''')
    cur.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (str(MAIN_ADMIN_ID),))
    
    cur.execute('''CREATE TABLE IF NOT EXISTS vps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        container_name TEXT UNIQUE NOT NULL,
        ram TEXT NOT NULL,
        cpu TEXT NOT NULL,
        storage TEXT NOT NULL,
        config TEXT NOT NULL,
        os_version TEXT DEFAULT 'ubuntu:22.04',
        status TEXT DEFAULT 'stopped',
        suspended INTEGER DEFAULT 0,
        whitelisted INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        shared_with TEXT DEFAULT '[]',
        suspension_history TEXT DEFAULT '[]',
        plan TEXT DEFAULT 'Standard'
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''')
    
    settings_init = [
        ('cpu_threshold', '90'),
        ('ram_threshold', '90'),
        ('auto_backup', '1'),
        ('maintenance_mode', '0'),
        ('vps_counter', '0'),
    ]
    for key, value in settings_init:
        cur.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    
    cur.execute('''CREATE TABLE IF NOT EXISTS port_allocations (
        user_id TEXT PRIMARY KEY,
        allocated_ports INTEGER DEFAULT 0
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS port_forwards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        vps_container TEXT NOT NULL,
        vps_port INTEGER NOT NULL,
        host_port INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        user_id TEXT NOT NULL,
        username TEXT NOT NULL,
        action TEXT NOT NULL,
        details TEXT NOT NULL
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        subject TEXT NOT NULL,
        status TEXT DEFAULT 'open',
        created_at TEXT NOT NULL,
        closed_at TEXT
    )''')
    
    conn.commit()
    conn.close()

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def truncate_text(text, max_length=1024):
    if not text:
        return text
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def get_setting(key: str, default: Any = None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def get_next_vps_number() -> int:
    """Get the next available VPS number"""
    conn = get_db()
    cur = conn.cursor()
    
    # Get current counter
    cur.execute('SELECT value FROM settings WHERE key = ?', ('vps_counter',))
    row = cur.fetchone()
    current = int(row[0]) if row else 0
    
    # Get all existing container names to check for gaps
    cur.execute('SELECT container_name FROM vps')
    existing = [row[0] for row in cur.fetchall()]
    conn.close()
    
    # Look for first available number starting from 1
    counter = 1
    while True:
        # Check if this number is already used in any container
        used = False
        for name in existing:
            # Extract number from container name if it matches pattern
            match = re.search(r'auranodez-(\d+)$', name)
            if match and int(match.group(1)) == counter:
                used = True
                break
        if not used:
            return counter
        counter += 1

def generate_container_name(username: str) -> str:
    """Generate a unique container name with the next available number"""
    number = get_next_vps_number()
    clean_name = re.sub(r'[^a-zA-Z0-9-]', '', username.lower())
    # Limit username length to avoid too long container names
    if len(clean_name) > 20:
        clean_name = clean_name[:20]
    return f"auranodez-{clean_name}-{number}"

def sync_containers():
    """Sync database with actual LXC containers"""
    conn = get_db()
    cur = conn.cursor()
    
    # Get all LXC containers
    try:
        result = subprocess.run(['lxc', 'list', '-c', 'n', '--format', 'csv'], 
                               capture_output=True, text=True)
        lxc_containers = set()
        for line in result.stdout.strip().split('\n'):
            if line:
                lxc_containers.add(line.strip())
    except Exception as e:
        logger.error(f"Failed to list LXC containers: {e}")
        conn.close()
        return
    
    # Get all containers in database
    cur.execute('SELECT container_name, id, user_id FROM vps')
    db_containers = {row[0]: {'id': row[1], 'user_id': row[2]} for row in cur.fetchall()}
    
    # Remove orphaned database entries (containers that don't exist in LXC)
    for name, data in db_containers.items():
        if name not in lxc_containers:
            logger.info(f"Removing orphaned database entry: {name}")
            cur.execute('DELETE FROM vps WHERE container_name = ?', (name,))
            cur.execute('DELETE FROM port_forwards WHERE vps_container = ?', (name,))
    
    # Add LXC containers that aren't in database (with placeholder data)
    for name in lxc_containers:
        if name not in db_containers:
            logger.info(f"Adding missing LXC container to database: {name}")
            # Try to get info from LXC
            try:
                info = subprocess.run(['lxc', 'info', name], capture_output=True, text=True)
                status = 'running' if 'Status: RUNNING' in info.stdout else 'stopped'
            except:
                status = 'stopped'
            
            # Extract user ID from container name if possible
            user_id = 'unknown'
            # Try to find if any user has this container
            for uid, vps_list in vps_data.items():
                for vps in vps_list:
                    if vps['container_name'] == name:
                        user_id = uid
                        break
                if user_id != 'unknown':
                    break
            
            cur.execute('''INSERT INTO vps (user_id, container_name, ram, cpu, storage, config, os_version, status, suspended, whitelisted, created_at, shared_with, suspension_history, plan)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (user_id, name, '1GB', '1', '10GB', 'Unknown', 'ubuntu:22.04', 
                         status, 0, 0, datetime.now().isoformat(), '[]', '[]', 'Unknown'))
    
    conn.commit()
    conn.close()

# ============================================================
# EMBED FUNCTIONS
# ============================================================

def create_embed(title, description="", color=EMBED_COLOR):
    embed = discord.Embed(
        title=f"✦ {BOT_NAME} — {title}",
        description=truncate_text(description, 4096),
        color=color
    )
    embed.set_thumbnail(url=BRAND_THUMBNAIL)
    embed.set_footer(text=f"{BRAND_FOOTER} • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                     icon_url=BRAND_LOGO)
    return embed

def add_field(embed, name, value, inline=False):
    embed.add_field(
        name=truncate_text(f"▸ {name}", 256),
        value=truncate_text(value, 1024),
        inline=inline
    )
    return embed

def create_success_embed(title, description=""):
    return create_embed(f"✅ {title}", description, color=SUCCESS_COLOR)

def create_error_embed(title, description=""):
    return create_embed(f"❌ {title}", description, color=ERROR_COLOR)

def create_info_embed(title, description=""):
    return create_embed(f"ℹ️ {title}", description, color=ACCENT_COLOR)

def create_warning_embed(title, description=""):
    return create_embed(f"⚠️ {title}", description, color=WARNING_COLOR)

# ============================================================
# ADMIN CHECKS
# ============================================================

def is_admin():
    async def predicate(ctx):
        user_id = str(ctx.author.id)
        if user_id == str(MAIN_ADMIN_ID) or user_id in admin_data.get("admins", []):
            return True
        raise commands.CheckFailure("You need admin permissions to use this command.")
    return commands.check(predicate)

def is_main_admin():
    async def predicate(ctx):
        if str(ctx.author.id) == str(MAIN_ADMIN_ID):
            return True
        raise commands.CheckFailure("Only the main admin can use this command.")
    return commands.check(predicate)

# ============================================================
# LXC COMMANDS
# ============================================================

async def execute_lxc(command, timeout=120):
    try:
        cmd = shlex.split(command)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise asyncio.TimeoutError(f"Command timed out after {timeout} seconds")
        
        if proc.returncode != 0:
            error = stderr.decode().strip() if stderr else "Command failed with no error output"
            raise Exception(error)
        return stdout.decode().strip() if stdout else True
    except Exception as e:
        logger.error(f"LXC Error: {command} - {str(e)}")
        raise

async def get_container_status(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "info", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()
        for line in output.splitlines():
            if line.startswith("Status: "):
                return line.split(": ", 1)[1].strip().lower()
        return "unknown"
    except Exception:
        return "unknown"

async def get_container_cpu_pct(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "top", "-bn1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()
        for line in output.splitlines():
            if '%Cpu(s):' in line:
                parts = line.split()
                us = float(parts[1])
                sy = float(parts[3])
                ni = float(parts[5])
                id_ = float(parts[7])
                wa = float(parts[9])
                hi = float(parts[11])
                si = float(parts[13])
                st = float(parts[15])
                return us + sy + ni + wa + hi + si + st
        return 0.0
    except Exception:
        return 0.0

async def get_container_ram_pct(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "free", "-m",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().splitlines()
        if len(lines) > 1:
            parts = lines[1].split()
            total = int(parts[1])
            used = int(parts[2])
            return (used / total * 100) if total > 0 else 0
        return 0.0
    except Exception:
        return 0.0

async def get_container_cpu(container_name):
    usage = await get_container_cpu_pct(container_name)
    return f"{usage:.1f}%"

async def get_container_memory(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "free", "-m",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().splitlines()
        if len(lines) > 1:
            parts = lines[1].split()
            total = int(parts[1])
            used = int(parts[2])
            return f"{used}/{total} MB"
        return "Unknown"
    except Exception:
        return "Unknown"

async def get_container_disk(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "df", "-h", "/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().splitlines()
        for line in lines:
            if '/dev/' in line and ' /' in line:
                parts = line.split()
                if len(parts) >= 5:
                    return f"{parts[2]}/{parts[1]} ({parts[4]})"
        return "Unknown"
    except Exception:
        return "Unknown"

async def get_container_uptime(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "uptime",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() if stdout else "Unknown"
    except Exception:
        return "Unknown"

async def apply_lxc_config(container_name):
    try:
        await execute_lxc(f"lxc config set {container_name} security.nesting true")
        await execute_lxc(f"lxc config set {container_name} security.privileged true")
        await execute_lxc(f"lxc config set {container_name} security.syscalls.intercept.mknod true")
        await execute_lxc(f"lxc config set {container_name} security.syscalls.intercept.setxattr true")
        
        try:
            await execute_lxc(f"lxc config device add {container_name} fuse unix-char path=/dev/fuse")
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise
        
        await execute_lxc(f"lxc config set {container_name} linux.kernel_modules overlay,loop,nf_nat,ip_tables,ip6_tables,netlink_diag,br_netfilter")
        
        raw_lxc_config = """
lxc.apparmor.profile = unconfined
lxc.cgroup.devices.allow = a
lxc.cap.drop =
lxc.mount.auto = proc:rw sys:rw cgroup:rw
"""
        await execute_lxc(f"lxc config set {container_name} raw.lxc '{raw_lxc_config}'")
        logger.info(f"Applied LXC config to {container_name}")
    except Exception as e:
        logger.error(f"Failed to apply LXC config to {container_name}: {e}")

async def apply_internal_permissions(container_name):
    try:
        await asyncio.sleep(3)
        commands = [
            "mkdir -p /etc/sysctl.d/",
            "echo 'net.ipv4.ip_unprivileged_port_start=0' > /etc/sysctl.d/99-custom.conf",
            "echo 'net.ipv4.ping_group_range=0 2147483647' >> /etc/sysctl.d/99-custom.conf",
            "echo 'fs.inotify.max_user_watches=524288' >> /etc/sysctl.d/99-custom.conf",
            "sysctl -p /etc/sysctl.d/99-custom.conf || true",
            "apt-get update -y > /dev/null 2>&1 || true",
            "apt-get install -y curl wget git vim htop net-tools > /dev/null 2>&1 || true"
        ]
        for cmd in commands:
            try:
                await execute_lxc(f"lxc exec {container_name} -- bash -c \"{cmd}\"")
            except Exception:
                continue
        logger.info(f"Applied internal permissions to {container_name}")
    except Exception as e:
        logger.error(f"Failed to apply internal permissions to {container_name}: {e}")

async def recreate_port_forwards(container_name: str) -> int:
    readded_count = 0
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT vps_port, host_port FROM port_forwards WHERE vps_container = ?', (container_name,))
    rows = cur.fetchall()
    for row in rows:
        vps_port = row['vps_port']
        host_port = row['host_port']
        try:
            await execute_lxc(f"lxc config device add {container_name} tcp_proxy_{host_port} proxy listen=tcp:0.0.0.0:{host_port} connect=tcp:127.0.0.1:{vps_port}")
            await execute_lxc(f"lxc config device add {container_name} udp_proxy_{host_port} proxy listen=udp:0.0.0.0:{host_port} connect=udp:127.0.0.1:{vps_port}")
            readded_count += 1
        except Exception as e:
            logger.error(f"Failed to re-add port forward {host_port}->{vps_port}: {e}")
    conn.close()
    return readded_count

# ============================================================
# PORT FORWARDING
# ============================================================

def get_user_allocation(user_id: 
