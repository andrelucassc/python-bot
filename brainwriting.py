import discord
from discord.ext import commands
import os
from database import Database
import logging
import datetime
import json
from bson import json_util
import random
from metrics import Metrics

log = logging.getLogger('brainwriting')

class Brainwriting(commands.Cog):
    """Category of Brainwriting"""
    def __init__(self):
        self.db = Database()
        self.collection = 'brainwriting_sessions'

    def currently_in_session(self):
        # is the brainwriting session started? TRUE=Yes and FALSE=No
        session_id = self.db.get_count(coll=self.collection) - 1
        log.info(f'currently_in_session: fetching data from last session ID: {session_id}')

        session = self.db.query(coll=self.collection, filtro={"id":session_id})
        log.debug(f'currently_in_session: session {session}')

        if session['finished'] == True:
            log.debug(f'currently_in_session: FINISHED: session retrieved sucessfully, ID {session_id}')
            return False
        else:
            log.debug(f'currently_in_session: IN_SESSION: session found but not finished, ID {session_id}')
            return True
    
    def kill_session(self):
        log.info('KILL_SESSION: ending session')
        message = "Finalizando Sessão"
        return message

    def iniciar_sessao(self):
        log.info('INICIAR_SESSAO: starting session message')
        message = "Iniciando sessão de brainwriting."
        return message
    
    def problema_sessao(self):
        log.info('PROBLEMA_SESSAO: problem message sent')
        return 'ERRO: Problema no Módulo de Brainwriting'
    
    @commands.command(name='start', help='MODERADOR: !start [chat_name]:default=chat')
    @commands.has_role('admin')
    async def startBrainwriting(self, ctx, chat_name='chat'):
        guild = ctx.guild

        existing_chat = discord.utils.get(guild.channels, name=chat_name+'_1')
        
        if existing_chat:
            if not self.currently_in_session():
                log.info(f'START: starting brainwriting session')
                await ctx.send(self.iniciar_sessao())

                session_id = self.db.get_count(coll=self.collection)
                session_data = {"id":session_id, "finished": False, "started_at": datetime.datetime.now(), "finished_at":""}
                
                self.db.insert_db(coll=self.collection, doc=session_data)
            else:
                log.error('START: not possible to start session, because one is already on session')
                await ctx.send('Não foi possível iniciar pois uma já está em sessão.')
        else:
            log.error(f'START: chat nao existente: {chat_name}_1')
            await ctx.send('Erro: não foi possível iniciar a sessão pois os canais de texto não foram criados')

    @commands.command(name='stop', help='MODERADOR: !stop')
    @commands.has_role('admin')
    async def stopBrainwriting(self, ctx):

        if self.currently_in_session():
            log.info(f'STOP: stopping brawriting session')
            await ctx.send(self.kill_session())

            session_id = self.db.get_count(coll=self.collection) - 1

            self.db.update_record(coll=self.collection, registro={ "id":session_id }, atualizacao={"finished": True, "finished_at":datetime.datetime.now()})

            metrics = Metrics

            await metrics.process_session(ctx=ctx)
            await metrics.put_gcp_session(ctx=ctx)
            await metrics.put_wit_session(ctx=ctx)

        else:
            log.error('STOP: not possible to stop session')
            await ctx.send('não foi possível terminar a sessão, pois não tem nenhuma em sessão.')

    @commands.command(name='idea', help='PARTICIPANTE: !idea [ideia] - Envia uma ideia')
    async def send_idea(self, ctx, *args):
        if self.currently_in_session:
            log.info(f'IDEA: enviando ideia de {ctx.author.name}')
            log.info({"id":ctx.message.id, "author":ctx.message.author.name, "content":' '.join(args), "created_at":datetime.datetime.now(), "updated_at":None})
            session_id = self.db.get_count(coll=self.collection) - 1
            self.db.insert_db(coll='raw_messages', doc={"id":ctx.message.id, "author":ctx.message.author.name, "content":' '.join(args), "session_id":session_id, "chat_id":ctx.channel.id, "created_at":datetime.datetime.now(), "updated_at":None})
        else:
            log.error(f'IDEA: could not send idea, because no session was started')
            await ctx.send('Erro ao enviar ideia. Nenhuma sessão foi iniciada ainda.')

    @commands.command(name='rotacionar', help='MODERADOR: !rotacionar - rotaciona os chats com as ideias')
    @commands.has_role('admin')
    async def rotate_ideas(self, ctx):
        if self.currently_in_session():
            log.info('ROTATE_IDEAS: rotating chats')
            await ctx.send('iniciando rotação entre chats')

            guild = ctx.guild
            chats = guild.channels
            under_chats = []
                        
            session_id = self.db.get_count(coll=self.collection) - 1
            log.info(f'ROTATE_IDEAS: session_id {session_id}')
            chats_messages = self.db.find(coll="raw_messages", filtro={"session_id":session_id})

            number_of_messages = [x["num_messages"] for x in self.db.agregar(coll='raw_messages', pipeline=[{ "$match": {"session_id":session_id} }, { "$count": "num_messages" }])]
            log.info(f'number of messages: {number_of_messages}')
            for channel in chats:
                if '_' in channel.name:
                    try:
                        log.info(f'ROTACIONAR: enviando mensagem de início para {channel.name}')
                        #await channel.send('iniciando rotação entre chats')
                        under_chats.append(channel)
                    except:
                        log.error('impossible to send|append message')
                else:
                    log.debug('not a channel to rotate')
            log.info(f'ROTACIONAR: under_chats: {under_chats}')       
            counter = 1
            for chat in chats_messages:

                try:
                    under_chats.remove(discord.utils.get(chats, id=chat["chat_id"]))
                except Exception as e:
                    log.error(f'POP: {e}')

                rand_channel = random.sample(under_chats, 1)
                canal_escolhido = rand_channel[0]
                log.info(f'picking channel: {rand_channel} and message: {chat["id"]}')
                log.info(f'under_chats: {under_chats}')
                try:
                    await canal_escolhido.send(f'Ideia número {counter}: '+chat["content"])
                except Exception as e:
                    log.error(f'ROTACIONAR: erro ao enviar conteudo: {chat["content"]} Error: {e}')
                counter += 1
                try:
                    under_chats.append(discord.utils.get(chats, id=chat["chat_id"]))
                except:
                    log.error('problem appending')

        else:
            await ctx.send('Nenhuma sessão Iniciada ainda')
            log.error('ROTATE_IDEAS: no current session found')
        
    @commands.command(name='cria_objetivo', help='MODERADOR: !cria_objetivo [objetivo]')
    @commands.has_role('admin')
    async def cadastrar_objetivo(self, ctx, *args):
        if self.currently_in_session():
            log.info('CADASTRAR_OBJETIVO: cadastrando objetivos')
            
            # must be minus 1 because it already exists and references a session and not a objective itself
            session_id = self.db.get_count(coll=self.collection) - 1 

            existing_objective = self.db.query(coll='objectives', filtro={"id":session_id})

            if existing_objective:
                log.info(f'objective for {session_id} already created')
            else:
                self.db.insert_db(coll='objectives', doc={"session_id": session_id, "created_at":datetime.datetime.now(), "objetivo":' '.join(args)})

            guild = ctx.guild
            chats = guild.channels

            for chat in chats:
                if "_" in chat.name:
                    log.debug(f'CADASTRAR_OBJETIVO: enviando para {chat.name}')
                    conteudo = 'Objetivo da sessão cadastrado: ' + ' '.join(args) + """\nPara repassar uma ideia, por favor escreva em uma única mensagem seu texto junto do comando !idea"""
                    await chat.send(content=conteudo)
                else:
                    log.debug(f'CADASTRAR_OBJETIVO: pass {chat.name}')


        else:
            log.error('CADASTRAR_OBJETIVO: nao foi possivel fazer o cadastro pois uma sessao nao foi iniciada.')
            await ctx.send('ERRO: Não foi possível fazer o cadastro')

    @commands.command(name='objetivo', help='PARTICIPANTE: !objetivo - mostra o objetivo da sessão')
    async def show_objetivo(self, ctx, *args):
        if self.currently_in_session():
            log.info(f'OBJETIVO: consultando banco de objetivos')
            guild = ctx.guild
            session_id = self.db.get_count(coll=self.collection) - 1 

            log.info(f'looking for session {session_id}')

            existing_objective = self.db.query(coll='objectives', filtro={"session_id":session_id})
            log.info(f'OBJETIVO: {existing_objective}')
            await ctx.send(content=existing_objective["objetivo"])
        else:
            log.error('OBJETIVO: nao foi possivel fazer o cadastro pois uma sessao nao foi iniciada.')
            await ctx.send('ERRO: Sessão não iniciada ainda.')


    @commands.command(name='pesquisar', help='PARTICIPANTE: !pesquisar - mostra o link de acesso a tela')
    async def pesquisar(self, ctx, *args):
        link = "https://app.powerbi.com/view?r=eyJrIjoiOTk2NTJiNGMtODQyOC00YmUwLWIwZmMtYWMwMjZiNzA0NDE2IiwidCI6ImYxYzM2NzE0LTgyNjAtNDhmNC1hOTU3LTI1OWZkOWQ1ZjVlMSJ9"
        await ctx.send(link)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            ctx.send("Argumento não aceito pelo bot.")

    
